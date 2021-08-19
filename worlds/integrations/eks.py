import boto3

from loguru import logger

def scale(**params):
    client = boto3.client('eks')
    client.update_nodegroup_config(**params)


def scale_up(pipeline, params):
    logger.info('Scaling Up: {}', pipeline)
    scale(
        clusterName=params['clusterName'],
        nodegroupName=params['nodegroupName'],
        scalingConfig=params['scaleUp'],
    )


def scale_down(pipeline, params):
    logger.info('Scaling Down: {}', pipeline)
    scale(
        clusterName=params['clusterName'],
        nodegroupName=params['nodegroupName'],
        scalingConfig=params['scaleDown'],
    )
