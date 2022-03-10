#!/bin/bash

# remove __pycache__ folders
rm -rf $(find ./app -name __pycache__)
# remove build and dist folders
rm -rf ./app/{build,dist}
