---
title: Parameter Tab
page_id: parameter_tab
---

The Crazyflie supports parameters, variables stored in the Crazyflie
that can be changed in real-time. The parameter tab can be used to view
and update parameters. For more information about parameters see
[logging and parameter frameworks](https://www.bitcraze.io/documentation/repository/crazyflie-firmware/master/userguides/logparam/).

![cfclient parameter list](/docs/images/cfclient_param.png){:align-center
width="700"}

1.  Parameter information fields
       * *Name:* The name of the parameter or group.
       * *Type:* The C-type of the variable stored in the Crazyflie (you cannot set values outside this)
       * *Access:* RW parameters can be written from the client while RO parameters can only be read
       * *Value:* The value of the parameter
    - Group: To make things easier each group has it's members organized as sub-nodes to the group
    - Parameters: The full name of each parameter is the group combined with the name (group.name)
