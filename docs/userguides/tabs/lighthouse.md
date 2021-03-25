---
title: Lighthouse Positioning Tab
page_id: lighthouse_tab
---

The Lighthouse Positioning tab shows information from the Lighthouse Positioning
system when present. It is also used to configure and manage the system.
For more information on how the Lighthouse system works, please see TODO

![cfclient positioning](/docs/images/cfclient_lh_main.png){:align-center width="700"}

The tab is divided into four sections:
1.  3D view of the Crazyfle and the base stations
2.  Crazyflie Status
3.  Base stations status
4.  System management

### 3D view
The view shows the position and orientation of the Crazyflie (blue) and the
base stations (green). The id of the base stations is displayed as a number and
the status as a color. Green means that data from the base station is used
in the position estimation.
The graph can be rotated by clicking and draging, zoomed using the scroll wheel
and moved by holding the shift key while clicking and draging.

### Crazyflie status
The overall status of the Lighthouse system is displayed as a text. The status is one of:
*  **LH ready** - one or more base stations are received and the information is used to estimate the position of the Crazyflie
*  **Not receiving** - no base station is received
*  **No geo/calib** - calibration or geometry data is missing and position can not be estimated

### Base station status
A detailed status of the base stations is indicated using colors in the grid. All
four sections for a base station must be green to work. When setting up the system
work from left to right and make sure all the boxes to the left are green.
1.  **Receiving** - green = light is received from the base station, red = no reception
2.  **Calibration** - indicates if there is calibration data for the base station or not.
Red = no calibration data, blue = calibration data from persistant storage but
not yet confirmed, green = calibration data has been received from the base station and
matched previous data, orange = calibration data has been received from the base station
but did **not** match the previous data, this means that you probably should redo the
geometry estimation.
3. **Geometry** - geometry data is available. Green = geometry data from persistant
storage or has been set from the client, red = no geometry data. Note: it is possible
that the geometry indicator is green even though the geometry data is not valid, this
is for instance the case if a base station is moved in a stystem that has been set
up earlier.
4.  **Estimator** - data from the base station is sent to the estimator to be used
in the position estimation process
Note: when Calibration data is receievd it is automatically stored in the persistant
memory to be available imetdiate after reboot.

### System Management
This section us used to configure the system.

* **Manage Geometry** - Opens a dialog box displaying the current geometry data. It
also contains a button to **Estimate Geometry** which calculates the position and
orientation of the base stations, using the Crazyflie postition as the origin.
The result is displayed together with the current geometry data, click the
**Write to Crazyflie** button to use the new geometry data. The new data is
also stored in the Crazyflie persistant storage to make it available after reboot.

* **Change system type** - Opens a dialog box where the system type can be changed.
Possible options are **Lighthouse V1** and **Lighthouse V2**.
Note: calibration and geometry data is erased when the system type is changed.

* **Set BS channel** - Opens a dialog box that is used to set the channel of a
base station. Connect **one** base station to the computer via USB and click
the **Scan basestation** button. If a base station is detected, a new channel
can be set by choosing the desired channel and clicking the “Set channel” button.

* **Save system config**/**Load system config** - store and load system configuration
to/from file, the system configuration contains system type, calibration and
geometry data.. When a system configuration is loaded from file it is automatically
written to the Crazyflie (and is stored in persistent memory). This is a
useful feature when configuring multiple Crazyflies for a system to make sure
they all share the same coordinate system.
