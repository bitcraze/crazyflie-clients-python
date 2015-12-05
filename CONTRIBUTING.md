# Crazyflie Python Client - Contributing

## Reporting issues

When reporting issues the more information you can supply the better. Since the client runs on many different OSes, can connect to multiple versions of the Crazyflie and you could use our official releases or clone directly from Git, it can be hard to figure out what's happening.

 - **Information about the environment:** The best is to C&P the information in the *About->Debug* dialog directly into the issue and supply the following information:
```
Host OS and version of OS:
Crazyflie/Crazyradio version:
Python version:
```
 - **How to reproduce the issue:** Step-by-step guide on how the issue can be reproduced (or at least how you reproduce it). Include everything you think might be useful, the more information the better.

## Improvements and ideas

If you would like to do bigger changes or have ideas on how to improve the client or lib, then post an issue and discuss it. We try to keep pushing changes on feature branches so you can see what we're up to. But it's always good to check with us first if you plan to make big changes, maybe it's something we are already working on or thinking about. If nothing else we might be able to contribute with some additional comments.

## Pull-requests

The development in this repository aims to follow the [Git flow](http://nvie.com/posts/a-successful-git-branching-model/) model. This means that pull-requests should be to the branch **develop** and not to **master**.  In order for the pull-request to be more easily accepted make sure to:

 - Test your changes and note what OS/version you have tested on
 - Describe the change
 - Refer to any issues it effects

Out goal is to comply with PEP-8, but there's lots of code that's not up to standard. We try our best to comply but since we slack sometimes we can't really enforce it, but at least there's a few things we want to stick to:

 - Don't include name, date or information about the change in the code. That's what Git is for.
 - CamelCase classes, but not functions and variables
 - Private variables and functions should start with _
 - 4 spaces indentation
 - When catching exceptions try to make it as specific as possible, it makes it harder for bugs to hide
 - Short variable and function names are ok if the scope is small

## CI-server

We use https://travis-ci.org/bitcraze/crazyflie-clients-python for continuous integration.
Initially we only check some PEP-8 properties, but the goal is to also add unit testing and integration testing. This is an ongoing effort.