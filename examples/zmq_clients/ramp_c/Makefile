LDFLAGS = -lzmq
CFLAGS = -std=c11
ramp: ramp.o
	cc $^ -o $@ $(LDFLAGS)
clean:
	rm -f *.o ramp
