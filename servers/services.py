import boto3
import time
import logging
from django.conf import settings
from .models import GameServer
 
logger = logging.getLogger(__name__)
 
 
# Risk profile → EC2 instance type
INSTANCE_TYPE_MAP = {
    "LOW":    "t3.small",    # ~$15/month  — low traffic
    "MEDIUM": "t3.medium",   # ~$30/month  — medium traffic
    "HIGH":   "t3.large",    # ~$60/month  — high traffic
}
 
# Max players ke hisaab se instance override
CAPACITY_INSTANCE_MAP = {
    500:   "t3.small",
    1000:  "t3.medium",
    5000:  "t3.large",
    10000: "c5.xlarge",
}
 
 
class AWSServerService:
    """
    Saara boto3 logic yahan hai.
    Views mein sirf yeh service use karo.
    """
 
    def _get_ec2_client(self, region: str):
        return boto3.client(
            "ec2",
            region_name=region,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
 
    def _get_instance_type(self, risk_profile: str, max_players: int) -> str:
        """Risk aur capacity dono dekho"""
        # Capacity se determine karo
        for capacity_limit, itype in sorted(CAPACITY_INSTANCE_MAP.items()):
            if max_players <= capacity_limit:
                return itype
        # Fallback — risk profile se
        return INSTANCE_TYPE_MAP.get(risk_profile, "t3.medium")
 
    def _get_user_data_script(self, server: "GameServer") -> str:
        """
        Instance start hote hi yeh script chalegi.
        Apna game server setup logic yahan daalo.
        """
        return f"""#!/bin/bash
set -e
apt-get update -y
apt-get install -y python3 python3-pip git
 
# Environment variables set karo
export ARENA_NAME="{server.arena_name}"
export MAX_PLAYERS="{server.max_players}"
export REGION="{server.region}"
export RISK_PROFILE="{server.risk_profile}"
export LIQUIDITY_SEED="{server.liquidity_seed}"
 
# Apna game server code clone/install karo
# git clone https://github.com/yourrepo/matka-game.git /app
# cd /app && pip3 install -r requirements.txt
# python3 manage.py runserver 0.0.0.0:8000
 
echo "Server {server.arena_name} started successfully" >> /var/log/game-server.log
"""
 
    def create_instance(self, server: "GameServer") -> dict:
        """
        EC2 instance banao aur instance_id return karo.
        GameServer object already DB mein save hona chahiye.
        """
        ec2 = self._get_ec2_client(server.region)
        instance_type = self._get_instance_type(server.risk_profile, server.max_players)
 
        try:
            response = ec2.run_instances(
                ImageId=settings.AWS_AMI_ID,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=1,
                KeyName=settings.AWS_KEY_PAIR,
                SecurityGroupIds=[settings.AWS_SECURITY_GROUP_ID],
                SubnetId=settings.AWS_SUBNET_ID,
                UserData=self._get_user_data_script(server),
 
                # Tags — AWS console mein identify karne ke liye
                TagSpecifications=[{
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name",           "Value": server.arena_name},
                        {"Key": "Project",        "Value": "matka-game"},
                        {"Key": "ArenaName",      "Value": server.arena_name},
                        {"Key": "Region",         "Value": server.region},
                        {"Key": "RiskProfile",    "Value": server.risk_profile},
                        {"Key": "MaxPlayers",     "Value": str(server.max_players)},
                        {"Key": "CreatedBy",      "Value": "admin-panel"},
                        {"Key": "DBServerId",     "Value": str(server.id)},
                    ]
                }]
            )
 
            instance = response["Instances"][0]
            return {
                "instance_id":   instance["InstanceId"],
                "instance_type": instance_type,
                "private_ip":    instance.get("PrivateIpAddress"),
                "public_ip":     instance.get("PublicIpAddress"),  # Launch pe null hoga
                "state":         instance["State"]["Name"],
            }
 
        except Exception as e:
            logger.error(f"EC2 create failed for {server.arena_name}: {e}")
            raise
 
    def get_instance_status(self, instance_id: str, region: str) -> dict:
        """Instance ka current status aur IP fetch karo"""
        ec2 = self._get_ec2_client(region)
 
        try:
            # Full instance details
            resp = ec2.describe_instances(InstanceIds=[instance_id])
            inst = resp["Reservations"][0]["Instances"][0]
 
            # Latency check
            start = time.time()
            ec2.describe_instance_status(InstanceIds=[instance_id])
            latency = int((time.time() - start) * 1000)
 
            aws_state = inst["State"]["Name"]  # pending/running/stopping/stopped/terminated
 
            # AWS state → humara status
            status_map = {
                "pending":     "launching",
                "running":     "healthy" if latency < 50 else "warming",
                "stopping":    "stopping",
                "stopped":     "stopped",
                "terminated":  "terminated",
                "shutting-down": "stopping",
            }
 
            return {
                "aws_state":  aws_state,
                "status":     status_map.get(aws_state, "degraded"),
                "public_ip":  inst.get("PublicIpAddress"),
                "private_ip": inst.get("PrivateIpAddress"),
                "latency_ms": latency,
            }
 
        except Exception as e:
            logger.error(f"Status check failed for {instance_id}: {e}")
            return {"status": "degraded", "latency_ms": 0, "public_ip": None}
 
    def stop_instance(self, instance_id: str, region: str):
        ec2 = self._get_ec2_client(region)
        ec2.stop_instances(InstanceIds=[instance_id])
        logger.info(f"Stopped instance {instance_id}")
 
    def start_instance(self, instance_id: str, region: str):
        ec2 = self._get_ec2_client(region)
        ec2.start_instances(InstanceIds=[instance_id])
        logger.info(f"Started instance {instance_id}")
 
    def terminate_instance(self, instance_id: str, region: str):
        ec2 = self._get_ec2_client(region)
        ec2.terminate_instances(InstanceIds=[instance_id])
        logger.info(f"Terminated instance {instance_id}")
 
    def list_all_servers_health(self) -> list:
        """
        Saare regions mein game servers ka health check.
        Admin panel ka server list page ke liye.
        """
        regions = [r[0] for r in GameServer.Region.choices]
        results = []
 
        for region in regions:
            ec2 = self._get_ec2_client(region)
            try:
                start = time.time()
                resp = ec2.describe_instances(
                    Filters=[
                        {"Name": "tag:Project", "Values": ["matka-game"]},
                        {"Name": "instance-state-name", "Values": ["running", "pending", "stopping"]}
                    ]
                )
                latency = int((time.time() - start) * 1000)
 
                for reservation in resp["Reservations"]:
                    for inst in reservation["Instances"]:
                        tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                        results.append({
                            "instance_id":  inst["InstanceId"],
                            "arena_name":   tags.get("ArenaName", inst["InstanceId"]),
                            "region":       region.upper(),
                            "status":       "healthy" if inst["State"]["Name"] == "running" else "warming",
                            "latency_ms":   latency,
                            "public_ip":    inst.get("PublicIpAddress"),
                            "instance_type": inst["InstanceType"],
                        })
            except Exception as e:
                logger.warning(f"Could not fetch servers in {region}: {e}")
 
        return results
 