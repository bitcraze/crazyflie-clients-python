---
title: Loco Positioning Tab
page_id: loco_tab
sort_order: 7
---

The Loco Positioning tab shows information from the Loco Positioning
system when present.

The bottom of the window shows a 3D view of the system. The
graphs can rotated by clicking and draging, zoomed using the scroll wheel
and moved by holding the shift key while clicking and draging.

The tab can be used in two modes that is selected with the radio buttons
to the right

To setup the LPS anchor system mode (TWR or TDoA), see the [Configure
LPS positioning mode wirelessly](https://www.bitcraze.io/documentation/repository/lps-node-firmware/master/) documentation.

### Position estimate mode

Displays the configured anchor positions and the estimated position of
the Crazyflie. Can be used to make sure the system is set up correctly
and that the estimated position is reasonable.

![cfclient positioning](/docs/images/cfclient_position_estimate.png)

1.  Plot showing anchors and Crazyflie
2.  Sets the graph mode
    -   *Position estimate* - Normal viewing mode
    -   *Anchor identification* - Enhanced mode where anchor id and
        marker becomes larger when Crazyflie is closer
3.  Indicates if anchors are communicating with Crazyflie (i.e anchors
    are up and running)
4.  Used to set anchor positions and change mode of the system

### Anchor position configuration

Click the ```Configure positions``` button top open the anghor position
dialog. In the dialog you can set the coordinates of the anchors. If an
anchor is missing, click ***** to add one more to the list.

The color of the fields has the following meanings:

-   *White* - No position exists for this anchor (i.e the position has
    not been read yet)
-   *Red* - Position has been read from the anchor and it differs from
    the currently shown value in the input box
-   *Green* - Position has been read from the anchor and it is the same
    as the currently shown value in the input box

The positions of the anchors is continuously read in the background and
as positions comes in or input box values changes the colors will be set
accordingly. There\'s also two buttons used for the settings:

-   *Get from anchors* - Fills the input boxes with the positions read
    from the anchors
-   *Write to anchors* - Writes the currently shown values in the input
    boxes to the anchors. In order to check that the write has been
    successful wait about 10s and all the fields should turn green as
    the positions are read back. If some of the fields are still red,
    try pressing the button again.

You can save anchor positions to file to store the setup for later use.
When you load positions from file the data in the input boxes will be
rplaced by the contents of the file.

### Anchor identification mode

displays the configured anchor positions. When the crazyflie is close to
an anchor this is indicated in the graphs by highlighting it. This mode
is useful to identify anchors and verify that the system is correctly
configured. **NOTE:** Only orks in TWR mode.

![cfclient anchors](/docs/images/cfclient_anchor_identification.png){:align-center
width="700"}

1.  Sets the graph mode
    -   *Position estimate* - Normal viewing mode
    -   *Anchor identification* - Enhanced mode where anchor id and
        marker becomes larger when Crazyflie is close to an anchor
2.  Plot showing anchors and Crazyflie. In this example anchor 1 is close
to the Crazyflie.
3.  Current system mode indication. The system must be in TWR mode for
    the anchor identification mode to be available.
