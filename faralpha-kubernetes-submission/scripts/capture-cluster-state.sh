#!/usr/bin/env bash
set -euo pipefail
mkdir -p screenshots
kubectl get nodes -o wide | tee screenshots/nodes.txt
kubectl get pods,svc,pvc,hpa -n faralpha -o wide | tee screenshots/resources.txt
kubectl describe hpa flask-app-hpa -n faralpha | tee screenshots/hpa-describe.txt
kubectl top pods -n faralpha | tee screenshots/pod-usage.txt
echo "Text evidence saved under screenshots/. Capture terminal screenshots manually for the submission."
