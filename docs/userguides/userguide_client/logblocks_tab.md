---
title: Log Blocks Tab
page_id: logblocks_tab
sort_order: 5
---

The log blocks tab shows all saved log configurations and lets you start/stop
them and write their data to file.

![cfclient log blocks](/docs/images/cfclient_logblocks_marked.png)

1.  Fields
    -   *ID:* Block ID on the Crazyflie
    -   *Name:* Block name in the client
    -   *Period (ms):* How often data is sent back to the client, in milliseconds
    -   *Start:* Checked if the block is running. Click to start or stop it.
        Note that some blocks drive the user interface — stopping them will
        cause parts of the UI to stop updating.
    -   *Write to file:* Checked if data is being written to file. Click to
        start or stop writing.
    -   *Contents:* The variables in the block, listed as `group.name`

2.  Each log block can be expanded to show its individual variables.

The data is written to the *logdata* folder in the client configuration directory
(find it via *Settings / Open config folder*). Files are organized into a
subdirectory per connection session, named by the connection timestamp.
Each file is named `{block_name}-{timestamp}.csv`. Starting and stopping file
writing multiple times within one session produces separate files.

The CSV format has a header row followed by one row per sample. The timestamp
column shows milliseconds since the Crazyflie was powered on.

Example data logged when logging the battery level:

    Timestamp,pm.vbat
    9103,3.74252200127
    10103,3.74252200127
    11103,3.74252200127
    12103,3.74252200127
    13103,3.74252200127
