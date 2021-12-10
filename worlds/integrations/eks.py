import boto3

from loguru import logger

def scale(cluster_name, pool_name, desired_size, min_size, max_size):
    logger.info('Scaling: {} {} {}', cluster_name, pool_name, desired_size)
    client = boto3.client('eks')
    client.update_nodegroup_config(
        clusterName=cluster_name,
        nodegroupName=pool_name,
        scalingConfig={'minSize': min_size, 'maxSize': max_size, 'desiredSize': desired_size},
    )
