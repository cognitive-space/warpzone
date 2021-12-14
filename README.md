# WarpZone

A magically easy way to run job pipelines on Kubernetes


## Developing

### kubectl Install

```
sudo apt-get update && sudo apt-get install -y apt-transport-https gnupg2
curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
echo "deb https://apt.kubernetes.io/ kubernetes-xenial main" | sudo tee -a /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update
sudo apt-get install -y kubectl
```

## Configure kubectl for Private Repo:

```
kubectl create secret docker-registry regcred --docker-server=https://gitlab.cog.space:5050 --docker-username=gitlab-ci-token --docker-password=<token> --docker-email=<email>
```

```json
{
  "eks": {
    "scaleUp": {
      "maxSize": 10,
      "minSize": 2,
      "desiredSize": 5
    },
    "scaleDown": {
      "maxSize": 10,
      "minSize": 2,
      "desiredSize": 2
    },
    "clusterName": "",
    "nodegroupName": ""
  }
}
```
