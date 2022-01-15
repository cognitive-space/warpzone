import os
from io import BytesIO
from zipfile import ZipFile, ZipInfo

from django import http
from django.contrib.auth.decorators import login_required
from django.template.response import TemplateResponse
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator

from warpzone.shelix_api import StarHelixApi
from worlds.models import Pipeline, Job, CompletedLog


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

    if job.shelix_log_id:
        return TemplateResponse(request, 'worlds/job_details_shelix.html', context)

    return TemplateResponse(request, 'worlds/job_details.html', context)


@login_required
def job_shelix_log(request, jid):
    job = get_object_or_404(Job, id=jid)

    after = request.GET.get('after', '')

    completed = CompletedLog.objects.filter(job=job).first()

    if completed:
        return http.JsonResponse({
            'job': job.to_json(),
            'url': completed.log_file.url
        })

    text, lastchunk, endlog = StarHelixApi.read_log(job.shelix_log_id, after)
    return http.JsonResponse({
        'text': text,
        'lastchunk': lastchunk,
        'job': job.to_json(),
        'endlog': endlog,
    })


@login_required
def job_log(request, jid, pod):
    log = get_object_or_404(CompletedLog, job_id=jid, pod=pod)
    if log.log_file:
        return http.HttpResponseRedirect(log.log_file.url)

    raise http.Http404


@login_required
def all_logs(request, jid, zip):
    job = get_object_or_404(Job, id=jid)

    new_zip = BytesIO()
    with ZipFile(new_zip, 'w') as new_archive:
        for log in CompletedLog.objects.filter(job=job):
            if log.log_file:
                contents = log.log_file.open('rb').read()
                new_archive.writestr(os.path.basename(log.log_file.name), contents)

    return http.HttpResponse(new_zip.getvalue(), content_type="application/zip")


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

        context = {
            'pipeline': pipeline.id,
            'image': image,
            'envs': envs,
        }
        if pipeline.cluster.needs_scale_up():
            pipeline.cluster.scale_up()
            return TemplateResponse(request, 'worlds/warmup_cluster.html', context)

        if not pipeline.cluster.warmed_up():
            context['warmup'] = True
            return TemplateResponse(request, 'worlds/warmup_cluster.html', context)

        warmup_hold = request.POST.get('warmup')
        if warmup_hold:
            context['wait'] = True
            return TemplateResponse(request, 'worlds/warmup_cluster.html', context)

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
