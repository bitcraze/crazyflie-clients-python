---
title: Log Client Tab
page_id: logclient_tab
sort_order: 11
---

The log client tab displays log messages produced by the client itself, such as
connection events, device scans, and gamepad detection. It is useful for
diagnosing client-side issues.

Log messages are shown in the format `LEVEL:LOGGER:MESSAGE`, for example:

    INFO:cfclient.ui.main:Connected to radio://0/80/2M
    WARNING:cfclient.ui.tabs.FlightTab:No input device found

Controls:

-   *Clear:* Removes all messages from the display.

![cfclient log blocks](/docs/images/cfclient_logclient.png)
