---
title: Tuning  Tab
page_id: tuning_tab
sort_order: 8
---

![cfclient plotter](/docs/images/tuning_tab.png)

This tab is for tuning the PID controller on your Crazyflie platform.

1. Select which part of the controller you want to tune (attitude (rate) or velocity/position)
2. Check the 'link roll and pitch' or 'link x and y' button if you have a symetrical platform, or else it is best to tune those seperately
3. Tune the PID gains of controller. This is best done within flight with the controller or flight commander
4. If you are not happy with your tuning, default to values there were in before
5. If you are happy, it would be best to persist the parameters so it is consistent after startup
6. If you want to remove the persistent parameter from the memory, you can also clear it.
