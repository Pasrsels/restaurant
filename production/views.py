from django.shortcuts import render
from django.views.generic import ListView
from .models import Production
from django.http import JsonResponse
from django.template.loader import render_to_string

class ProductionListView(ListView):
    model = Production
    template_name = "production/production_list.html"
    context_object_name = "productions"
    paginate_by = 10
    ordering = ['-created']

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        queryset = queryset.filter(branch=user.branch) 
        return queryset.select_related("branch")

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            productions_html = render_to_string(
                "production/_production_list_items.html",
                {"productions": context["productions"]},
                request=self.request,
            )
            return JsonResponse({
                "productions_html": productions_html,
                "has_next": context["productions"].has_next(),
            })
        else:
            return super().render_to_response(context, **response_kwargs)