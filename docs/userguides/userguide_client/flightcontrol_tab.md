---
title: Flightcontrol Tab
page_id: flightcontrol_tab
sort_order: 1
---

The normal view used when flying is the one seen below.

![cfclient flighttab](/docs/images/cfclient_flightab.png)

1.  Flight mode selector (Normal and Advanced)
    * *Normal:* Recommended for beginners
    * *Advanced:* Will unlock flight settings in 3

2.  Assisted mode selection. The assisted mode is enabled when the assisted mode
    button is pressed on the Gamepad.
    * *Altitude hold*: Keeps the Crazyflie at its current altitude automatically. Thrust control becomes height velocity control.
    * *Position hold*: Keeps the Crazyflie at its current 3D position. Pitch/Roll/Thrust control becomes X/Y/Z velocity control.
    * *Height hold*: When activated, keeps the Crazyflie at 40cm above the ground. Thrust control becomes height velocity control. Requires a height sensor like the [Z-Ranger deck](https://www.bitcraze.io/products/z-ranger-deck-v2/).
    * *Hover*: When activated, keeps the Crazyflie at 40cm above the ground and tries to
    keep the position in X and Y as well. Thrust control becomes height velocity
    control. Requires a flow deck. Uses body-fixed coordinates.
3. Roll/pitch trim can be set either in the UI or using the controller (if the correct buttons are mapped).
    This will offset the input to the Crazyflie for correcting imbalance and reducing drift.
4. Advanced flight control settings are available if Advanced mode has been selected (settings are in %):
    * *Max angle:* Set the max roll/pitch angle allowed
    * *Max yaw rate:*Set the max yaw rate allowed
    * *Max thrust:* Set the max thrust allowed
    * *Min thrust:* Minimum thrust before 0 is sent to the Crazyflie
    * *Slew limit:* Set the percentage where the thrust is slew controlled (the thrust value lowering will be limited). This makes the Crazyflie a bit easier to fly for beginners
    * *Slew rate:* When the thrust is below the slew limit, this is the maximum rate of lowering the thrust
5. Settings for flight decks, currently the LED-ring effect and headlights can be set (if the ring is attached)
6. Target values sent from the client for controlling the Crazyflie
7. Actual values logged from the Crazyflie
8. Motor output on the Crazyflie
9. Horizon indicator
10. Command based flight control, allow controlled flight if, and only if, a positioning deck such as the [Flow deck](https://store.bitcraze.io/collections/decks/products/flow-deck-v2), the [Loco deck](https://store.bitcraze.io/collections/decks/products/loco-positioning-deck) or the [Lighthouse deck](https://store.bitcraze.io/collections/decks/products/lighthouse-positioning-deck) is present.
11. Arming/disarming button. Pressing this will send a arming or disarming event to the Crazyflie which will arm or disarm the system if this is possible. This button can also say "Auto arming" which indicates the crazyflie is configured to arm the system automatically if system checks have passed. More info in [crazyflie firmware arming documentation](https://www.bitcraze.io/documentation/repository/crazyflie-firmware/master/functional-areas/supervisor/arming/). 