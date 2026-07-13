#!/bin/bash

for i in {16..31}; do echo 0 | sudo tee /sys/devices/system/cpu/cpu${i}/online; done
