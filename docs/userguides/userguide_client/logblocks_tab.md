---
title: Log Blocks Tab
page_id: logblocks_tab
sort_order: 5
---

The log blocks tab shows all log configurations that are saved and if
they are started. It\'s also possible to start/stop them as well as
write the logged data to file.

![cfclient log blocks](/docs/images/cfclient_logblocks_marked.png)

1.  Fields
    -   *ID:* Block id in Crazyflie
    -   *Name:* Block name in client
    -   *Period:* The period of which the data is sent back to the
        client
    -   *Start:* Marked if started, click to start/stop block. Note that
        some of the blocks are used for the user interface, so if they
        are stopped the user interface will stop updating
    -   *Write to <file:*> Marked if writing to file, clock to
        start/stop writing. The data will be written in the
        configuration folder for the client (see \<here\> how to find
        it).
    -   *Contents:* The variables contained in the block (named by
        group.name)
2.  Information for log configurations are folded by group by default,
    opening them up will show in detail what variables are in the group

 The data written to file will be in
the configuration folder under *logdata*. Each directory is timestamped
after when the client was started and each file timestamped after when
the writing to file was started (i.e starting/stopping and
starting/stopping again will yield two files in the same directory). The
data logged to the file is in CSV format with the headers for the data
at the top. A timestamp is automatically added for each entry and shows
the number of milliseconds passed since the Crazyflie started (sent
together with the log data).

Example data
of what\'s logged when logging the battery level:

    Timestamp,pm.vbat
    9103,3.74252200127
    10103,3.74252200127
    11103,3.74252200127
    12103,3.74252200127
    13103,3.74252200127
