---
title: Log TOC Tab
page_id: logtoc_tab
sort_order: 6
---

The log TOC (Table of Contents) tab shows all log variables available on the
connected Crazyflie. It is a read-only reference for what can be logged —
use the [Log Blocks tab](logblocks_tab.md) to configure and start logging.

Variables are grouped by category and displayed in a sortable tree.

![cfclient log blocks](/docs/images/cfclient_logtoc.png)

1.  Fields
    -   *Name:* The variable or group name
    -   *ID:* Numerical identifier of the variable on the Crazyflie
    -   *Unpack:* Python type used to unpack the received data
    -   *Storage:* C type used to store the value on the Crazyflie
    -   *Description:* Short description of the variable, if documentation is available

2.  The tree is grouped by category. Expanding a group shows all variables within it.

The tab is populated automatically when a Crazyflie connects and cleared when it disconnects.
