# Terraform — AWS EKS

Provisions a VPC + managed EKS cluster + ECR repository for this project.

## ⚠️ This costs real money — read before running

- EKS control plane: **~$0.10/hr (~$73/month)** flat, regardless of cluster size.
- 2× `t3.medium` worker nodes: **~$0.08/hr total**.
- 1 NAT gateway: **~$0.045/hr + data processing**.
- A LoadBalancer Service (if you create one) adds an ELB: **~$0.025/hr**.

**Recommended usage for a portfolio project:** `terraform apply` right before you
record your demo, confirm everything works, take your screenshots/video, then
immediately `terraform destroy`. A couple of hours of use costs well under $2.

## Usage

```bash
cd infra/terraform
terraform init
terraform plan      # review before applying — this is the step recruiters picture you running
terraform apply
aws eks update-kubeconfig --region ap-south-1 --name devops-portfolio
kubectl get nodes   # confirm the cluster is live before deploying the app

# ... deploy k8s/ manifests, test, record your demo ...

terraform destroy   # do not skip this — leaving EKS running is the #1 way this project gets expensive
```

## Remote state

By default this uses local state (a `terraform.tfstate` file on disk) so it
works immediately. Before you treat this as a "real" setup, create an S3
bucket + DynamoDB table for locking, then uncomment the `backend "s3"` block
in `main.tf`. This is a detail worth mentioning in interviews: it's *why*
teams don't just run Terraform from a laptop.
