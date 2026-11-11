# Assignemnt
## FarAlpha Intern Assignment — Flask, MongoDB and Kubernetes

This repository implements **Part 2** of the supplied assignment: a Flask API deployed with at least two replicas, authenticated MongoDB in a StatefulSet, internal/external service access, persistent storage, HPA, DNS, and resource requests/limits.


## 1. Architecture

- Flask application: Docker image, Deployment starts with 2 replicas.
- Flask Service: `ClusterIP`; access locally using `kubectl port-forward`.
- MongoDB: one-replica StatefulSet, root authentication enabled from a Kubernetes Secret.
- MongoDB Services: `mongodb` ClusterIP for application connections and `mongodb-headless` for StatefulSet network identity.
- Persistence: static 2 GiB hostPath PV on the Minikube node, bound to a PVC mounted at `/data/db`.
- Autoscaling: HPA targets average CPU utilization of 70%, with 2–5 replicas.
- Both Flask and MongoDB pods request `200m CPU / 250Mi memory` and have limits `500m CPU / 500Mi memory`.

## 2. Prerequisites

Install:
- Docker
- kubectl
- Minikube
- Python 3.10+ (for local tests and load generator)

Start a cluster with enough capacity for the pod resource requests:

```bash
minikube start --cpus=4 --memory=6144
minikube addons enable metrics-server
kubectl get nodes
kubectl top nodes
```

Wait until `kubectl top nodes` returns metrics. HPA CPU metrics depend on Metrics Server.

## 3. Build the Flask image

From the repository root:

```bash
docker build -t faralpha/flask-mongodb-app:1.0 .
```

### Option A — use the image directly in Minikube (simplest local route)

```bash
minikube image load faralpha/flask-mongodb-app:1.0
```

The Deployment manifest already references this image and uses `IfNotPresent`.

### Option B — push to a registry

Replace `YOUR_DOCKERHUB_USERNAME` with your registry username:

```bash
docker tag faralpha/flask-mongodb-app:1.0 YOUR_DOCKERHUB_USERNAME/flask-mongodb-app:1.0
docker login
docker push YOUR_DOCKERHUB_USERNAME/flask-mongodb-app:1.0
```

Then update `image:` in `k8s/flask.yaml` to
`YOUR_DOCKERHUB_USERNAME/flask-mongodb-app:1.0` and apply that manifest.

## 4. Deploy to Kubernetes

Apply in this order:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/mongodb-secret.yaml
kubectl apply -f k8s/mongodb-pv-pvc.yaml
kubectl apply -f k8s/mongodb.yaml
kubectl apply -f k8s/flask.yaml
kubectl apply -f k8s/flask-hpa.yaml
```

Watch readiness:

```bash
kubectl get pv
kubectl get pvc -n faralpha
kubectl get pods -n faralpha -w
```

Check all resources:

```bash
kubectl get all -n faralpha
kubectl get hpa -n faralpha
kubectl describe hpa flask-app-hpa -n faralpha
```

Expected initial state: one MongoDB pod, two Flask pods, one bound PVC, and HPA minimum replicas set to 2. HPA metrics may show `<unknown>` briefly while Metrics Server gathers data.

## 5. Test the API

In a separate terminal, forward the Flask Service to localhost:

```bash
kubectl port-forward -n faralpha service/flask-service 5000:80
```

In another terminal:

```bash
curl http://127.0.0.1:5000/
curl -i -X POST http://127.0.0.1:5000/data \
  -H 'Content-Type: application/json' \
  -d '{"sampleKey":"sampleValue"}'
curl http://127.0.0.1:5000/data
```

Expected POST response: HTTP `201` and `{"status":"Data inserted"}`. The GET response should contain the inserted document. Repeat the POST and GET to confirm MongoDB persistence.

Check database authentication and logs:

```bash
kubectl logs -n faralpha statefulset/mongodb
kubectl describe pod -n faralpha -l app=mongodb
```

The Flask connection URI is injected using Secret-backed environment variables. It connects to `mongodb.faralpha.svc.cluster.local:27017/flask_db` and authenticates against MongoDB's `admin` database (`authSource=admin`).

## 6. Autoscaling test

Keep the port-forward running. In another terminal, start a load test:

```bash
python scripts/load_test.py --url http://127.0.0.1:5000 --requests 3000 --workers 100
```

While load is running, sample HPA and pods:

```bash
kubectl get hpa flask-app-hpa -n faralpha -w
kubectl get pods -n faralpha -w
```

In a separate terminal, capture a snapshot:

```bash
kubectl get hpa flask-app-hpa -n faralpha
kubectl top pods -n faralpha
kubectl get deployment flask-app -n faralpha
```

HPA scales when observed average CPU utilization exceeds 70%; it may take time for metrics collection and scale-up. If CPU does not exceed the target, increase request count/workers or run the load test longer. The HPA is capped at 5 replicas. After load stops, Kubernetes gradually scales down subject to its stabilization behavior.

The load generator writes a JSON summary to stdout. Paste the **actual** summary and the HPA/pod observations into the results table below. Do not use expected values as measured results.

### Test results to complete after running on your cluster

| Scenario | Command / evidence | Actual result |
|---|---|---|
| Flask root endpoint | `curl http://127.0.0.1:5000/` | Fill in HTTP status and response |
| Insert document | POST `/data` | Fill in HTTP status and response |
| Retrieve document | GET `/data` | Fill in returned document |
| Initial replicas | `kubectl get deployment flask-app -n faralpha` | Fill in ready/desired count |
| HPA under load | `kubectl get hpa -n faralpha` during load | Fill in CPU %, current and desired replicas |
| Scale ceiling | `kubectl get hpa -n faralpha` under sustained load | Confirm desired replicas never exceed 5 |
| Persistence | Delete/recreate Flask pod, then GET `/data` | Confirm inserted document remains |
| Database authentication | Flask logs and successful API calls | Record whether authenticated connection succeeded |

### Issues / observations

Record only issues actually encountered. Useful things to check if a test fails:
- HPA reports unknown CPU: Metrics Server is not ready, or resource requests are missing.
- ImagePullBackOff: image was not loaded into Minikube or the image name differs.
- PVC Pending: check PV/PVC storage class, capacity and Minikube hostPath.
- Flask cannot connect to MongoDB: check MongoDB pod readiness, Secret keys, service DNS, and `authSource=admin`.
- HPA does not scale: verify CPU load actually exceeds 70% of requested CPU and allow time for metrics and control-loop intervals.

## 7. DNS resolution inside Kubernetes

Kubernetes DNS (normally CoreDNS) creates DNS records for Services. A pod in the `faralpha` namespace can resolve the MongoDB Service by its short name `mongodb`; its fully qualified DNS name is:

`mongodb.faralpha.svc.cluster.local`

The Flask application uses this Service DNS name in `MONGODB_URI`. The Service selects pods with label `app: mongodb` and forwards TCP port 27017 to the MongoDB pod. This avoids hard-coding a pod IP, which can change when a pod is recreated. The headless Service `mongodb-headless` supplies stable StatefulSet network identity; the regular ClusterIP Service provides a stable virtual IP and load-balancing endpoint within the cluster.

## 8. Resource requests and limits

A **request** is the amount Kubernetes uses when scheduling a pod and the baseline used for resource-based HPA utilization calculations. A **limit** is the maximum resource amount the container may consume. CPU above its limit is throttled; memory above its limit can cause the container to be terminated with an out-of-memory (OOM) event.

This assignment uses the requested sample values for both workloads:

| Workload | CPU request | Memory request | CPU limit | Memory limit |
|---|---:|---:|---:|---:|
| Flask | 200m | 250Mi | 500m | 500Mi |
| MongoDB | 200m | 250Mi | 500m | 500Mi |

The Flask HPA target of 70% means an average CPU target of approximately 140m per pod when each pod requests 200m CPU. Requests and limits help the scheduler place workloads, reduce noisy-neighbor effects, and provide predictable resource boundaries. These are sample lab values, not production sizing recommendations.

## 9. Design choices and alternatives

1. **Deployment for Flask:** Flask instances are stateless, so a Deployment is appropriate and supports rolling updates and horizontal scaling. A StatefulSet is unnecessary for the API.
2. **StatefulSet for MongoDB:** MongoDB is stateful and benefits from stable pod identity and persistent storage. One replica is used for this local assignment; it is not a highly available MongoDB replica set.
3. **ClusterIP for MongoDB:** Database traffic remains inside the cluster. A NodePort or LoadBalancer would unnecessarily expose the database.
4. **ClusterIP plus port-forward for Flask:** The service is reachable inside the cluster; `kubectl port-forward` makes it accessible from the developer machine without exposing a public endpoint. NodePort or Ingress could be used for a longer-lived external access requirement.
5. **Secret for credentials:** Credentials are not embedded in the Flask source or image. Kubernetes Secret values are base64-encoded and are not encrypted merely by being base64; enable encryption at rest and restrict RBAC in production.
6. **PersistentVolume + PVC:** The PVC decouples the pod from the storage implementation. `hostPath` is simple for a single-node Minikube exercise; a dynamic StorageClass or cloud block storage is preferable outside a local lab.
7. **HPA with CPU:** CPU utilization is easy to demonstrate and matches the task. For production, consider memory/custom metrics, workload latency, and queue depth as additional signals.
8. **Gunicorn:** A production WSGI server is used instead of Flask's development server. The container runs as a non-root user.

## 10. Security and cleanup notes

The included Secret is a **demo credential** so the assignment can be deployed without editing multiple files. Change it before sharing or using outside a disposable local cluster. The password is not a production secret. Do not commit real credentials to source control.

To remove the assignment resources:

```bash
kubectl delete namespace faralpha
kubectl delete pv mongodb-pv
```

Because the PV reclaim policy is `Retain`, the Minikube node's `/data/mongodb` data is retained. Remove it only if you intentionally want to erase the local database data.

## 11. Submission checklist

- [x] Flask application source and `/` + `/data` endpoints
- [x] Dockerfile and dependency file
- [x] Kubernetes YAML for Namespace, Secret, PV, PVC, MongoDB StatefulSet, Services, Flask Deployment and HPA
- [x] README with build, deploy, access, DNS and resource explanations
- [x] Load-test script and unit tests
- [ ] Run the cluster deployment and tests on Minikube
- [ ] Add real HPA/CPU/pod output and actual load-test summary to the results table
- [ ] Add genuine screenshots to `screenshots/` (see below)

### Screenshots to capture for the final email

Capture screenshots from your own terminal after running the commands:
1. `kubectl get pods -n faralpha` showing Flask replicas and MongoDB ready.
2. `kubectl get pvc -n faralpha` showing the claim Bound.
3. `kubectl get hpa -n faralpha` during load showing CPU and replica counts.
4. `kubectl top pods -n faralpha` during load.
5. Successful POST and GET requests to `/data`.

Save the images in `screenshots/` and reference them in this README before sending the assignment. The text snapshots produced by `scripts/capture-cluster-state.sh` are supporting evidence, not substitutes for screenshots.

## 12. Local unit tests

The unit tests mock MongoDB and check the HTTP contract without requiring a running database:

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install pytest
pytest -q
```
