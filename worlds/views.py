from io import BytesIO
from zipfile import ZipFile, ZipInfo

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
        envs = request.POST.get('envs')
        pipeline = get_object_or_404(Pipeline, id=request.POST['pipeline'])
        qjob, job = pipeline.run_job(image, command, envs)
        return http.HttpResponseRedirect(f'/worlds/job/{job.id}/')

    pipelines = []
    for p in Pipeline.objects.all().order_by('name'):
        pipelines.append({'text': p.name, 'value': p.id})

    context = {
        'pipelines': pipelines
    }
    return TemplateResponse(request, 'worlds/start_job.html', context)


@login_required
def job_list(request):
    jobs = Job.objects.all().select_related('pipeline').defer('job_definition')
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
def job_zip(self, jid, zip):
    job = get_object_or_404(Job, id=jid)

    base_path = job.pipeline.get_job_storage()
    path = base_path / job.job_name
    files = path.glob('**/*')

    new_zip = BytesIO()
    with ZipFile(new_zip, 'w') as new_archive:
        for file in files:
            contents = file.open('rb').read()
            relpath = str(file)
            relpath = relpath.replace(str(base_path), '')
            new_archive.writestr(relpath, contents)

    return http.HttpResponse(new_zip.getvalue(), content_type="application/zip")

@login_required
def job_kill(request, jid):
    job = get_object_or_404(Job, id=jid)
    job.kill()
    return http.HttpResponseRedirect("/")


@login_required
def pipeline_list(request):
    pipes = Pipeline.objects.all().order_by('name')
    paginator = Paginator(pipes, 50)

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'page_obj': page_obj
    }
    return TemplateResponse(request, 'worlds/pipeline_list.html', context)


@login_required
def start_pipeline(request):
    if request.method == 'POST':
        image = request.POST['image']
        envs = request.POST.get('envs')
        pipeline = get_object_or_404(Pipeline, id=request.POST['pipeline'])
        qjob = pipeline.start_pipeline(image, envs)
        return http.HttpResponseRedirect(f'/worlds/job/{qjob.id}/')

    pipelines = []
    for p in Pipeline.objects.all().order_by('name'):
        pipelines.append({'text': p.name, 'value': p.id})

    context = {
        'pipelines': pipelines
    }
    return TemplateResponse(request, 'worlds/start_pipeline.html', context)


def favicon(request):
    return http.HttpResponseRedirect("/static/favicon.ico")
