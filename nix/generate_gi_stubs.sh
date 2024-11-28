#!/usr/bin/env bash

cd ..
echo $shellHook | grep '^#' | sed 's/^#//' | while IFS= read -r line; do
    echo "Executing: $line"
    eval "$line"
done