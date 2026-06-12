#!/usr/bin/env python3
"""Guarded 5 cm HLC hover using transformed mocap positions and extpos only."""
import argparse, csv, json, math, time
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from threading import Lock, Thread

DEFAULT_URI="radio://0/80/2M"; DEFAULT_HOST="192.168.1.42:3883"; DEFAULT_BODY="crazyflie_21"
DEFAULT_PROOF=".cache/mocap-autonomy-emergency-stop-proof.json"
LOG_PERIOD_MS=100; LOOP_S=.05; MOCAP_STALE_S=.30; ESTIMATOR_STALE_S=.50
GROUND_ALTITUDE_M=.02; GROUND_DISPLACEMENT_LIMIT_M=.05; AIRBORNE_LATERAL_LIMIT_M=.03

@dataclass(frozen=True)
class PositionSample: raw:tuple; local:tuple; timestamp:float; frame_count:int
@dataclass(frozen=True)
class YawBaseline: yaw_deg:float
@dataclass(frozen=True)
class GuardResult: estimator_error_m:float; lateral_error_m:float; lateral_limit_m:float; yaw_error_deg:float; height_m:float
@dataclass(frozen=True)
class EmergencyStopResult:
    zero_thrust_sent:int
    stop_setpoints_sent:int
    disarm_requested:bool
    confirmed_disarmed:bool
class GuardTrip(RuntimeError):
    def __init__(self,reason,immediate_stop): super().__init__(reason); self.reason=reason; self.immediate_stop=immediate_stop

class GuardDebouncer:
    def __init__(self): self.since={}
    def exceeded(self,name,active,duration,now):
        if not active:
            self.since.pop(name,None);return False
        self.since.setdefault(name,now)
        return now-self.since[name]>=duration

def finite(v): return isinstance(v,Real) and math.isfinite(float(v))
def vector(v): return v is not None and len(v)==3 and all(finite(x) for x in v)
def distance(a,b): return math.sqrt(sum((a[i]-b[i])**2 for i in range(3)))
def angle_error_deg(a,b): return (a-b+180)%360-180
def transform_mocap_position(raw,origin):
    if not vector(raw) or not vector(origin): raise ValueError("finite XYZ values required")
    return (-(raw[1]-origin[1]),raw[0]-origin[0],raw[2]-origin[2])
def floor_origin_target(height):
    if not finite(height) or height<0: raise ValueError("height must be non-negative")
    return (0.,0.,float(height))
def takeoff_event(height): return f"takeoff absolute_z={float(height):.3f}"
def lateral_limit_for_phase(phase,z): return GROUND_DISPLACEMENT_LIMIT_M if phase=="takeoff" and z<GROUND_ALTITUDE_M else AIRBORNE_LATERAL_LIMIT_M
def classify_failure(exc): return "emergency" if isinstance(exc,KeyboardInterrupt) or isinstance(exc,GuardTrip) and exc.immediate_stop else "controlled-land"

def load_runtime_modules():
    import cflib.crtp, motioncapture
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
    from cflib.utils.reset_estimator import reset_estimator
    return cflib.crtp,motioncapture,Crazyflie,LogConfig,SyncCrazyflie,reset_estimator

class MocapState:
    def __init__(self): self.lock=Lock(); self.sample=None
    def update(self,raw,local):
        with self.lock: self.sample=PositionSample(tuple(raw),tuple(local),time.time(),1 if self.sample is None else self.sample.frame_count+1)
    def snapshot(self):
        with self.lock: return self.sample
class TelemetryState:
    def __init__(self): self.lock=Lock(); self.values={}; self.times={}
    def update(self,group,values):
        with self.lock: self.values.update(values); self.times[group]=time.time()
    def snapshot(self):
        with self.lock: return dict(self.values),dict(self.times)
class ExtposStream:
    def __init__(self,cf,origin,state): self.cf=cf; self.origin=origin; self.state=state; self.lock=Lock(); self.sent=0; self.errors=0; self.last_error=""
    def send(self,x,y,z):
        raw=(x,y,z); local=transform_mocap_position(raw,self.origin)
        with self.lock:
            try: self.cf.extpos.send_extpos(*local)
            except Exception as exc: self.errors+=1; self.last_error=str(exc); raise
            self.sent+=1; self.last_error=""
        self.state.update(raw,local)
    def snapshot(self):
        with self.lock: return {"extpos_sent_count":self.sent,"extpos_error_count":self.errors,"extpos_last_error":self.last_error}
class MocapReader(Thread):
    def __init__(self,module,host,body):
        super().__init__(daemon=True); self.module=module; self.host=host; self.body=body; self.on_position=None; self.error=None; self.running=True; self.lock=Lock(); self.connection_lock=Lock(); self.connection=None; self.raw=None; self.timestamp=0.; self.frames=0
    def raw_snapshot(self):
        with self.lock: return self.raw,self.timestamp,self.frames
    @staticmethod
    def release(c):
        for name in ("close","disconnect","shutdown"):
            method=getattr(c,name,None) if c else None
            if callable(method):
                try: method()
                except Exception: pass
    def close(self):
        self.running=False; self.on_position=None
        with self.connection_lock: c,self.connection=self.connection,None
        self.release(c)
    def run(self):
        c=None
        try:
            c=self.module.connect("vrpn",{"hostname":self.host})
            with self.connection_lock: self.connection=c
            while self.running:
                c.waitForNextFrame(); body=c.rigidBodies.get(self.body)
                if body is None: continue
                raw=tuple(float(v) for v in body.position)
                with self.lock: self.raw,self.timestamp,self.frames=raw,time.time(),self.frames+1
                if self.on_position: self.on_position(*raw)
                body=None
        except Exception as exc:
            if self.running: self.error=exc
        finally:
            with self.connection_lock: release=self.connection is c; self.connection=None if release else self.connection
            if release: self.release(c)

class CsvLogger:
    FIELDS="""wall_time_s elapsed_s mode phase target_local_x target_local_y target_local_z raw_mocap_x raw_mocap_y raw_mocap_z local_mocap_x local_mocap_y local_mocap_z mocap_age_s mocap_frame_count floor_origin_raw_x floor_origin_raw_y floor_origin_raw_z stateEstimate.x stateEstimate.y stateEstimate.z stateEstimate.vx stateEstimate.vy stateEstimate.vz stateEstimate.roll stateEstimate.pitch stateEstimate.yaw stabilizer.roll stabilizer.pitch stabilizer.yaw estimator_age_s attitude_age_s velocity_age_s estimator_mocap_error_m lateral_error_m lateral_limit_m height_m height_limit_m yaw_baseline_deg yaw_error_deg pm.vbat motor.m1 motor.m2 motor.m3 motor.m4 extpos_sent_count extpos_error_count extpos_last_error hlc_command_event guard_result stop_reason""".split()
    def __init__(self,path,mode): path.parent.mkdir(parents=True,exist_ok=True); self.file=path.open("w",newline=""); self.writer=csv.DictWriter(self.file,fieldnames=self.FIELDS); self.writer.writeheader(); self.mode=mode; self.started=time.time()
    def write(self,row): now=time.time(); full={"wall_time_s":now,"elapsed_s":now-self.started,"mode":self.mode}; full.update(row); self.writer.writerow(full); self.file.flush()
    def close(self): self.file.close()

def setup_telemetry(cf,LogConfig,state):
    groups=(("position",("stateEstimate.x","stateEstimate.y","stateEstimate.z"),True),("velocity",("stateEstimate.vx","stateEstimate.vy","stateEstimate.vz"),True),("attitude",("stateEstimate.roll","stateEstimate.pitch","stateEstimate.yaw"),True),("stabilizer",("stabilizer.roll","stabilizer.pitch","stabilizer.yaw"),False),("power",("pm.vbat",),True),("motor",("motor.m1","motor.m2","motor.m3","motor.m4"),False)); started=[]
    for name,names,required in groups:
        try:
            cfg=LogConfig(name=name,period_in_ms=LOG_PERIOD_MS)
            for item in names: cfg.add_variable(item,"uint16_t" if item.startswith("motor.") else "float")
            cfg.data_received_cb.add_callback(lambda timestamp,data,logconf:state.update(logconf.name,data)); cf.log.add_config(cfg); cfg.start(); started.append(cfg)
        except Exception as exc:
            if required: raise RuntimeError(f"Required telemetry {name} unavailable: {exc}") from exc
            print(f"[WARN] Optional telemetry {name} unavailable: {exc}")
    return started
def packet_age(times,group,now=None): now=time.time() if now is None else now; return float("inf") if not times.get(group) else now-times[group]
def estimate_position(values):
    p=tuple(values.get(n) for n in ("stateEstimate.x","stateEstimate.y","stateEstimate.z")); return p if vector(p) else None

def evaluate_guards(args,sample,values,times,baseline,phase,now=None,debouncer=None):
    now=time.time() if now is None else now; immediate=phase!="preflight"
    if sample is None or now-sample.timestamp>MOCAP_STALE_S: raise GuardTrip("stale mocap telemetry",True)
    if any(packet_age(times,g,now)>ESTIMATOR_STALE_S for g in ("position","velocity","attitude","power")): raise GuardTrip("stale estimator telemetry",True)
    estimate=estimate_position(values)
    if estimate is None: raise GuardTrip("invalid estimator position",True)
    battery=values.get("pm.vbat")
    if not finite(battery): raise GuardTrip("battery telemetry invalid",True)
    roll,pitch,yaw=(values.get(n) for n in ("stateEstimate.roll","stateEstimate.pitch","stateEstimate.yaw"))
    if not all(finite(v) for v in (roll,pitch,yaw)): raise GuardTrip("invalid attitude telemetry",True)
    if phase=="preflight":
        if battery<args.min_battery_v: raise GuardTrip("battery unacceptable for preflight",False)
        if abs(roll)>args.max_level_deg or abs(pitch)>args.max_level_deg: raise GuardTrip("roll/pitch exceeds preflight limit",False)
    else:
        debouncer=debouncer or GuardDebouncer();tilt=max(abs(roll),abs(pitch))
        if debouncer.exceeded("critical_battery",battery<args.critical_battery_v,args.critical_guard_debounce_s,now): raise GuardTrip(f"battery {battery:.2f}V below critical limit",True)
        if debouncer.exceeded("landing_battery",battery<args.landing_battery_v,args.landing_guard_debounce_s,now): raise GuardTrip(f"battery {battery:.2f}V below landing limit",False)
        if debouncer.exceeded("critical_tilt",tilt>args.critical_tilt_deg,args.critical_guard_debounce_s,now): raise GuardTrip(f"roll/pitch {tilt:.1f}deg exceeds critical limit",True)
        if debouncer.exceeded("landing_tilt",tilt>args.landing_tilt_deg,args.landing_guard_debounce_s,now): raise GuardTrip(f"roll/pitch {tilt:.1f}deg exceeds landing limit",False)
    yaw_error=abs(angle_error_deg(yaw,baseline.yaw_deg)); yaw_limit=args.max_preflight_yaw_error_deg if phase=="preflight" else args.max_flight_yaw_error_deg
    if yaw_error>yaw_limit: raise GuardTrip(f"yaw error {yaw_error:.1f}deg exceeds {yaw_limit:.1f}deg",immediate)
    error=distance(sample.local,estimate); error_limit=args.max_estimator_error_m if phase=="preflight" else args.emergency_estimator_error_m
    if error>error_limit: raise GuardTrip(f"estimator/mocap error {error:.3f}m exceeds {error_limit:.3f}m",immediate)
    height=sample.local[2]
    if height>args.max_local_height_m: raise GuardTrip("excessive height",True)
    lateral=math.hypot(sample.local[0],sample.local[1]); lateral_limit=lateral_limit_for_phase(phase,height)
    if phase!="preflight" and lateral>lateral_limit: raise GuardTrip(f"{phase} lateral error {lateral:.3f}m exceeds {lateral_limit:.3f}m",True)
    return GuardResult(error,lateral,lateral_limit,yaw_error,height)

def log_sample(logger,args,origin,mocap,telemetry,stream,baseline,phase,target,event="",guard="ok",reason=""):
    sample=mocap.snapshot(); values,times=telemetry.snapshot(); now=time.time(); raw=sample.raw if sample else ("",)*3; local=sample.local if sample else ("",)*3; estimate=estimate_position(values); yaw=values.get("stateEstimate.yaw")
    row={"phase":phase,"target_local_x":target[0],"target_local_y":target[1],"target_local_z":target[2],"raw_mocap_x":raw[0],"raw_mocap_y":raw[1],"raw_mocap_z":raw[2],"local_mocap_x":local[0],"local_mocap_y":local[1],"local_mocap_z":local[2],"mocap_age_s":now-sample.timestamp if sample else "","mocap_frame_count":sample.frame_count if sample else 0,"floor_origin_raw_x":origin[0],"floor_origin_raw_y":origin[1],"floor_origin_raw_z":origin[2],"estimator_age_s":packet_age(times,"position",now),"attitude_age_s":packet_age(times,"attitude",now),"velocity_age_s":packet_age(times,"velocity",now),"estimator_mocap_error_m":distance(local,estimate) if sample and estimate else "","lateral_error_m":math.hypot(local[0],local[1]) if sample else "","lateral_limit_m":lateral_limit_for_phase(phase,local[2]) if sample and phase!="preflight" else "","height_m":local[2] if sample else "","height_limit_m":args.max_local_height_m,"yaw_baseline_deg":baseline.yaw_deg if baseline else "","yaw_error_deg":abs(angle_error_deg(yaw,baseline.yaw_deg)) if baseline and finite(yaw) else "","hlc_command_event":event,"guard_result":guard,"stop_reason":reason}
    for name in ("stateEstimate.x","stateEstimate.y","stateEstimate.z","stateEstimate.vx","stateEstimate.vy","stateEstimate.vz","stateEstimate.roll","stateEstimate.pitch","stateEstimate.yaw","stabilizer.roll","stabilizer.pitch","stabilizer.yaw","pm.vbat","motor.m1","motor.m2","motor.m3","motor.m4"): row[name]=values.get(name,"")
    row.update(stream.snapshot()); logger.write(row)

def wait_raw(reader):
    deadline=time.time()+8
    while time.time()<deadline:
        raw,t,_=reader.raw_snapshot()
        if vector(raw) and time.time()-t<=MOCAP_STALE_S:return
        if reader.error:raise RuntimeError(reader.error)
        time.sleep(LOOP_S)
    raise RuntimeError("No fresh mocap")
def capture_origin(args,reader):
    print("[FLOOR] Place level nose-front drone at exact takeoff pose."); input("Press ENTER to capture local zero..."); samples=[]; deadline=time.time()+args.floor_capture_duration
    while time.time()<deadline:
        raw,t,_=reader.raw_snapshot()
        if not vector(raw) or time.time()-t>MOCAP_STALE_S:raise RuntimeError("Mocap stale during floor capture")
        samples.append(raw);time.sleep(LOOP_S)
    ranges=[max(s[i] for s in samples)-min(s[i] for s in samples) for i in range(3)]
    if max(ranges)>args.max_floor_spread_m:raise RuntimeError("Floor pose moved")
    return tuple(sorted(s[i] for s in samples)[len(samples)//2] for i in range(3))
def wait_telemetry(state):
    deadline=time.time()+8
    while time.time()<deadline:
        values,times=state.snapshot()
        if estimate_position(values) and all(packet_age(times,g)<=ESTIMATOR_STALE_S for g in ("position","velocity","attitude","power")):return
        time.sleep(LOOP_S)
    raise RuntimeError("Telemetry unavailable")
def capture_baseline(args,state):
    samples=[];deadline=time.time()+args.preflight_duration
    while time.time()<deadline:
        values,times=state.snapshot(); roll,pitch,yaw=(values.get(n) for n in ("stateEstimate.roll","stateEstimate.pitch","stateEstimate.yaw"))
        if packet_age(times,"attitude")>ESTIMATOR_STALE_S or not all(finite(v) for v in (roll,pitch,yaw)):raise RuntimeError("Attitude stale")
        if abs(roll)>args.max_level_deg or abs(pitch)>args.max_level_deg:raise RuntimeError("Drone not level")
        samples.append(yaw);time.sleep(LOOP_S)
    ref=samples[0];values=sorted(ref+angle_error_deg(v,ref) for v in samples);baseline=(values[len(values)//2]+180)%360-180
    if abs(angle_error_deg(baseline,args.expected_yaw_deg))>args.max_preflight_yaw_error_deg:raise RuntimeError("Yaw baseline not aligned to validated nose-front")
    return YawBaseline(baseline)
def require_preflight(args,reader,mocap,telemetry,stream,logger,origin,baseline):
    deadline=time.monotonic()+args.preflight_timeout;stable=None;last=""
    while time.monotonic()<deadline:
        values,times=telemetry.snapshot()
        try:r=evaluate_guards(args,mocap.snapshot(),values,times,baseline,"preflight")
        except GuardTrip as exc:stable=None;last=exc.reason;log_sample(logger,args,origin,mocap,telemetry,stream,baseline,"preflight",(0,0,0),guard="reject",reason=last)
        else:
            stable=time.monotonic() if stable is None else stable;log_sample(logger,args,origin,mocap,telemetry,stream,baseline,"preflight",(0,0,0))
            if time.monotonic()-stable>=args.preflight_duration:print(f"[PREFLIGHT] PASS error={r.estimator_error_m:.3f}m");return
        if reader.error:raise RuntimeError(reader.error)
        time.sleep(LOOP_S)
    raise RuntimeError(f"Preflight failed: {last}")
def monitor(args,logger,origin,reader,mocap,telemetry,stream,baseline,phase,target,duration):
    deadline=time.time()+duration;debouncer=GuardDebouncer()
    while time.time()<deadline:
        values,times=telemetry.snapshot()
        try:evaluate_guards(args,mocap.snapshot(),values,times,baseline,phase,debouncer=debouncer)
        except GuardTrip as exc:log_sample(logger,args,origin,mocap,telemetry,stream,baseline,phase,target,guard="trip",reason=exc.reason);raise
        log_sample(logger,args,origin,mocap,telemetry,stream,baseline,phase,target)
        if reader.error:raise GuardTrip("mocap reader failed",True)
        time.sleep(LOOP_S)

def wait_supervisor_state(cf,attribute,expected,timeout=2.0):
    deadline=time.time()+timeout
    while time.time()<deadline:
        try:
            if bool(getattr(cf.supervisor,attribute)) is expected:return True
        except Exception:pass
        time.sleep(.1)
    return False
def arm(cf):
    request_sent=False
    try:
        cf.supervisor.send_arming_request(True);request_sent=True
        if wait_supervisor_state(cf,"is_armed",True):return
        raise RuntimeError("Arm confirmation timed out")
    except BaseException as exc:
        if request_sent:
            result=emergency_stop(cf)
            raise RuntimeError("Arming state uncertain; emergency cleanup confirmed_disarmed="+str(result.confirmed_disarmed)) from exc
        raise
def disarm(cf):
    try:cf.supervisor.send_arming_request(False);return True
    except Exception:
        try:cf.platform.send_arming_request(False);return True
        except Exception:return False
def emergency_stop(cf):
    print("[SAFETY] EMERGENCY STOP")
    try:cf.high_level_commander.stop()
    except Exception:pass
    zero_sent=0;stop_sent=0
    for _ in range(40):
        try:cf.commander.send_setpoint(0.,0.,0.,0);zero_sent+=1
        except Exception:pass
        try:cf.commander.send_stop_setpoint();stop_sent+=1
        except Exception:pass
        time.sleep(.01)
    disarm_requested=disarm(cf);confirmed_disarmed=wait_supervisor_state(cf,"is_armed",False)
    return EmergencyStopResult(zero_sent,stop_sent,disarm_requested,confirmed_disarmed)
def controlled_land(cf,args,logger,origin,reader,mocap,telemetry,stream,baseline,reason):
    target=(0.,0.,0.);log_sample(logger,args,origin,mocap,telemetry,stream,baseline,"controlled-land",target,event="land absolute_z=0",guard="active",reason=reason)
    try:cf.high_level_commander.land(0.,args.land_duration,yaw=None);monitor(args,logger,origin,reader,mocap,telemetry,stream,baseline,"controlled-land",target,args.land_duration+.25);cf.high_level_commander.stop();disarm(cf)
    except BaseException:emergency_stop(cf);raise
def write_proof(path,args,result):
    if not result.confirmed_disarmed or not result.disarm_requested or result.zero_thrust_sent<40 or result.stop_setpoints_sent<40: raise RuntimeError("Emergency stop was not fully verified; hover remains locked")
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps({"completed_at":time.time(),"uri":args.uri,"rigid_body":args.rigid_body,"test":"props-off-ctrl-c-active-hlc-emergency-stop","zero_thrust_sent":result.zero_thrust_sent,"stop_setpoints_sent":result.stop_setpoints_sent,"disarm_requested":result.disarm_requested,"confirmed_disarmed":result.confirmed_disarmed})+"\n")
def require_emergency_proof(path,args,now=None):
    now=time.time() if now is None else now
    try:p=json.loads(Path(path).read_text())
    except (OSError,ValueError) as exc:raise ValueError("hover is locked until emergency-test completes successfully") from exc
    if p.get("test")!="props-off-ctrl-c-active-hlc-emergency-stop" or p.get("uri")!=args.uri or p.get("rigid_body")!=args.rigid_body:raise ValueError("emergency proof mismatch")
    if p.get("zero_thrust_sent",0)<40 or p.get("stop_setpoints_sent",0)<40 or p.get("disarm_requested") is not True or p.get("confirmed_disarmed") is not True:raise ValueError("emergency proof is incomplete")
    if not 0<=now-float(p.get("completed_at",0))<=86400:raise ValueError("emergency proof expired")
def run_emergency_test(cf,args):
    print("[PROPS-OFF] REMOVE ALL PROPELLERS")
    if input("Type PROPS OFF: ")!="PROPS OFF":raise RuntimeError("Confirmation failed")
    input("Press ENTER to arm and activate HLC...");arm(cf)
    try:
        cf.high_level_commander.takeoff(0.,30.,yaw=None)
        if not wait_supervisor_state(cf,"hl_control_active",True):raise RuntimeError("HLC did not become active")
        print("[PROPS-OFF] HLC is active. Press Ctrl+C now.")
        while True:time.sleep(.25)
    except KeyboardInterrupt:
        result=emergency_stop(cf);write_proof(args.emergency_proof,args,result);print("[PROPS-OFF] PASS: active-HLC Ctrl+C stop and disarm verified")
    except BaseException:emergency_stop(cf);raise
def run_hover(cf,args,logger,origin,reader,mocap,telemetry,stream,baseline):
    hover=(0.,0.,args.height);floor=(0.,0.,0.);armed=False
    try:
        input("Press ENTER to ARM and run 5 cm hover...");arm(cf);armed=True
        log_sample(logger,args,origin,mocap,telemetry,stream,baseline,"takeoff",hover,event=takeoff_event(args.height),guard="active");cf.high_level_commander.takeoff(args.height,args.takeoff_duration,yaw=None);monitor(args,logger,origin,reader,mocap,telemetry,stream,baseline,"takeoff",hover,args.takeoff_duration+.25)
        if mocap.snapshot().local[2]<.7*args.height:raise GuardTrip("takeoff too low",False)
        monitor(args,logger,origin,reader,mocap,telemetry,stream,baseline,"hover",hover,args.hover_duration)
        log_sample(logger,args,origin,mocap,telemetry,stream,baseline,"land",floor,event="land absolute_z=0",guard="active");cf.high_level_commander.land(0.,args.land_duration,yaw=None);monitor(args,logger,origin,reader,mocap,telemetry,stream,baseline,"land",floor,args.land_duration+.25);cf.high_level_commander.stop();disarm(cf);armed=False
    except BaseException as exc:
        log_sample(logger,args,origin,mocap,telemetry,stream,baseline,"stop",floor,event="stop",guard="failed",reason=str(exc))
        if armed:
            emergency_stop(cf) if classify_failure(exc)=="emergency" else controlled_land(cf,args,logger,origin,reader,mocap,telemetry,stream,baseline,str(exc));armed=False
        raise
    finally:
        if armed:emergency_stop(cf)

def validate_args(args):
    if args.mode in ("x-step","y-step","figure8"):raise ValueError(f"{args.mode} is locked until hover is explicitly proven")
    if args.max_estimator_error_m>args.emergency_estimator_error_m or args.height>=args.max_local_height_m:raise ValueError("invalid limits")
    if not args.critical_battery_v<args.landing_battery_v<args.min_battery_v:raise ValueError("battery thresholds must be critical < landing < preflight")
    if not args.max_level_deg<args.landing_tilt_deg<args.critical_tilt_deg:raise ValueError("tilt thresholds must be preflight < landing < critical")
    if args.mode=="hover":require_emergency_proof(args.emergency_proof,args)
def run(args):
    validate_args(args);crtp,motioncapture,Crazyflie,LogConfig,SyncCrazyflie,reset_estimator=load_runtime_modules();crtp.init_drivers();path=Path(args.output) if args.output else Path(args.output_dir)/f"mocap-autonomy-{args.mode}-{time.strftime('%Y%m%d-%H%M%S')}.csv";logger=CsvLogger(path,args.mode);reader=MocapReader(motioncapture,args.mocap_host,args.rigid_body);mocap=MocapState();telemetry=TelemetryState();configs=[]
    print("local X=-raw Y; local Y=+raw X; local Z=+raw Z; extpos only")
    try:
        input("Press ENTER to connect mocap...");reader.start();wait_raw(reader);origin=capture_origin(args,reader);input("Press ENTER to connect Crazyflie...")
        with SyncCrazyflie(args.uri,cf=Crazyflie(rw_cache="./cache")) as scf:
            cf=scf.cf;configs=setup_telemetry(cf,LogConfig,telemetry);stream=ExtposStream(cf,origin,mocap);reader.on_position=stream.send;cf.param.set_value("stabilizer.estimator","2");cf.param.set_value("commander.enHighLevel","1");time.sleep(.5);reset_estimator(cf);time.sleep(args.settle_duration);wait_telemetry(telemetry);baseline=capture_baseline(args,telemetry);require_preflight(args,reader,mocap,telemetry,stream,logger,origin,baseline);run_emergency_test(cf,args) if args.mode=="emergency-test" else run_hover(cf,args,logger,origin,reader,mocap,telemetry,stream,baseline)
    finally:
        for cfg in configs:
            try:cfg.stop()
            except Exception:pass
        reader.close();reader.join(timeout=2) if reader.ident else None;logger.close()
def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("mode",choices=("emergency-test","hover","x-step","y-step","figure8"));p.add_argument("--uri",default=DEFAULT_URI);p.add_argument("--mocap-host",default=DEFAULT_HOST);p.add_argument("--rigid-body",default=DEFAULT_BODY);p.add_argument("--output-dir",default="flight_logs");p.add_argument("--output");p.add_argument("--emergency-proof",default=DEFAULT_PROOF);p.add_argument("--height",type=float,default=.05);p.add_argument("--takeoff-duration",type=float,default=5.);p.add_argument("--hover-duration",type=float,default=2.);p.add_argument("--land-duration",type=float,default=6.);p.add_argument("--floor-capture-duration",type=float,default=2.);p.add_argument("--max-floor-spread-m",type=float,default=.01);p.add_argument("--settle-duration",type=float,default=2.);p.add_argument("--preflight-duration",type=float,default=2.);p.add_argument("--preflight-timeout",type=float,default=12.);p.add_argument("--min-battery-v",type=float,default=3.75);p.add_argument("--landing-battery-v",type=float,default=3.60);p.add_argument("--critical-battery-v",type=float,default=3.30);p.add_argument("--landing-tilt-deg",type=float,default=10.);p.add_argument("--critical-tilt-deg",type=float,default=20.);p.add_argument("--landing-guard-debounce-s",type=float,default=1.);p.add_argument("--critical-guard-debounce-s",type=float,default=.25);p.add_argument("--max-estimator-error-m",type=float,default=.05);p.add_argument("--emergency-estimator-error-m",type=float,default=.08);p.add_argument("--max-level-deg",type=float,default=5.);p.add_argument("--expected-yaw-deg",type=float,default=0.);p.add_argument("--max-preflight-yaw-error-deg",type=float,default=5.);p.add_argument("--max-flight-yaw-error-deg",type=float,default=10.);p.add_argument("--max-local-height-m",type=float,default=.12);return p.parse_args(argv)
if __name__=="__main__":run(parse_args())
