from django import http
from django.contrib.auth.decorators import login_required
from django.template.response import TemplateResponse
from django.shortcuts import get_object_or_404

from worlds.models import Pipeline, Job


@login_required
def start_job(request):
    if request.method == 'POST':
        image = request.POST['image']
        command = request.POST['command']
        pipeline = get_object_or_404(Pipeline, id=request.POST['pipeline'])
        qjob, job = pipeline.run_job(image, command)
        return http.HttpResponseRedirect(f'/worlds/job/{job.id}/')

    pipelines = []
    for p in Pipeline.objects.all():
        pipelines.append({'text': p.name, 'value': p.id})

    context = {
        'pipelines': pipelines
    }
    return TemplateResponse(request, 'worlds/start_job.html', context)


@login_required
def job_details(request, jid):
    job = get_object_or_404(Job, id=jid)
    context = {
        'job': job
    }
    return TemplateResponse(request, 'worlds/job_details.html', context)


@login_required
def job_kill(request, jid):
    job = get_object_or_404(Job, id=jid)
    job.kill()
    return http.HttpResponseRedirect("/")
