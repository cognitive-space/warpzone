from django import http
from django.contrib.auth.decorators import login_required
from django.template.response import TemplateResponse
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator

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
def job_list(request):
    jobs = Job.objects.all()
    paginator = Paginator(jobs, 50)

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'page_obj': page_obj
    }
    return TemplateResponse(request, 'worlds/job_list.html', context)

@login_required
def job_details(request, jid):
    job = get_object_or_404(Job, id=jid)
    context = {
        'job': job
    }
    return TemplateResponse(request, 'worlds/job_details.html', context)

@login_required
def job_log(request, jid, pod):
    job = get_object_or_404(Job, id=jid)
    if job.log_data and pod in job.log_data:
        return http.HttpResponse(job.log_data[pod], content_type="text/plain")

    raise http.Http404

@login_required
def job_kill(request, jid):
    job = get_object_or_404(Job, id=jid)
    job.kill()
    return http.HttpResponseRedirect("/")


def favicon(request):
    return http.HttpResponseRedirect("/static/favicon.ico")
