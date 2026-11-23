import os
from django.views.generic import View
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden
from django.template.loader import get_template
from django.conf import settings
from django.contrib.staticfiles import finders
from xhtml2pdf import pisa
from io import BytesIO
from .models import BucketList

def link_callback(uri, rel):
    """
    Convert HTML images/stylesheets with relative paths to absolute filesystem paths
    so xhtml2pdf can load them from disk.
    """
    sUrl = settings.STATIC_URL      # e.g. '/static/'
    mUrl = settings.MEDIA_URL      # e.g. '/media/'

    # Normalize lead slash and static/media prefixes to prevent SuspiciousFileOperation
    clean_uri = uri
    if clean_uri.startswith(sUrl):
        clean_uri = clean_uri.replace(sUrl, "", 1)
    elif '/static/' in clean_uri:
        clean_uri = clean_uri.split('/static/')[-1]
    elif clean_uri.startswith(mUrl):
        clean_uri = clean_uri.replace(mUrl, "", 1)
    elif '/media/' in clean_uri:
        clean_uri = clean_uri.split('/media/')[-1]

    # Remove leading slashes to keep path relative for safe_join
    clean_uri = clean_uri.lstrip('/')

    # use finders to find static files safely in development/production
    result = finders.find(clean_uri)
    if result:
        if not isinstance(result, (list, tuple)):
            result = [result]
        return result[0]
        
    # fallback to static/media roots
    sRoot = str(settings.STATIC_ROOT)    # e.g. '/workspace/staticfiles/'
    mRoot = str(settings.MEDIA_ROOT)

    if uri.startswith(mUrl):
        path = os.path.join(mRoot, uri.replace(mUrl, "", 1).lstrip('/'))
    elif uri.startswith(sUrl) or '/static/' in uri:
        path = os.path.join(sRoot, clean_uri)
    else:
        # Check in local static directories directly
        for static_dir in settings.STATICFILES_DIRS:
            test_path = os.path.join(str(static_dir), clean_uri)
            if os.path.isfile(test_path):
                return test_path
        return uri

    # make sure that file exists
    if not os.path.isfile(path):
        return uri
    return path

def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html  = template.render(context_dict)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result, link_callback=link_callback)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return None

class ExportListPDFView(View):
    def get(self, request, pk):
        bucket = get_object_or_404(BucketList, id=pk)
        # Check access
        is_owner = bucket.owner == request.user
        is_shared = request.user.is_authenticated and request.user in bucket.shared_with.all()
        if not (is_owner or is_shared or bucket.is_public):
            return HttpResponseForbidden("Zugriff verweigert.")
            
        tpl = bucket.category.template
        raw_pdf = (tpl.get_ui_style().get('pdf') or {}) if hasattr(tpl, 'get_ui_style') else {}
        pdf_cfg = {
            'orientation': raw_pdf.get('orientation') if raw_pdf.get('orientation') in ('portrait', 'landscape') else 'portrait',
            'filter': request.GET.get('filter') or raw_pdf.get('filter') or 'all',
            'include_summary': raw_pdf.get('include_summary', True),
            'include_notes': raw_pdf.get('include_notes', True),
            'include_photos': raw_pdf.get('include_photos', True),
            'include_subchecklist': raw_pdf.get('include_subchecklist', True),
            'include_custom_fields': raw_pdf.get('include_custom_fields', True),
            'include_persons': raw_pdf.get('include_persons', True),
            'include_dates': raw_pdf.get('include_dates', True),
            'footer_text': raw_pdf.get('footer_text', ''),
        }

        all_items = list(
            bucket.items.select_related('domain_category', 'created_by')
            .prefetch_related('images', 'person_roles__person')
            .all()
        )
        total_count = len(all_items)
        done_count = sum(1 for i in all_items if i.is_completed)
        open_count = total_count - done_count

        if pdf_cfg['filter'] == 'open':
            items = [i for i in all_items if not i.is_completed]
        elif pdf_cfg['filter'] == 'done':
            items = [i for i in all_items if i.is_completed]
        else:
            items = all_items

        total_price = sum(float(i.price) for i in items if i.price is not None) if tpl.use_price else None

        context = {
            'bucket': bucket,
            'items': items,
            'template_config': tpl,
            'pdf_cfg': pdf_cfg,
            'total_count': total_count,
            'open_count': open_count,
            'done_count': done_count,
            'total_price': total_price,
        }
        
        response = render_to_pdf('core/pdf_export.html', context)
        if response:
            filename = f"{bucket.title}.pdf"
            content = f"inline; filename={filename}"
            response['Content-Disposition'] = content
            return response
        return HttpResponse("Fehler bei der PDF-Generierung", status=500)
