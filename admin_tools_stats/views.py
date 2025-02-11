import logging
import time
from collections import OrderedDict
from datetime import datetime
from typing import Dict, List, Union

from datetime_truncate import truncate
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from .models import DashboardStats, Interval, get_charts_timezone, truncate_ceiling, get_dynamic_choices_array, CriteriaToStatsM2M


logger = logging.getLogger(__name__)


class AdminChartsView(TemplateView):
    template_name = "admin_tools_stats/admin_charts.js"


interval_dateformat_map_bar_chart = {
    "years": ("%Y", "%Y"),
    "quarters": ("%b %Y", "%b"),
    "months": ("%b %Y", "%b"),
    "weeks": ("%a %d %b %Y", "%W"),
    "days": ("%a %d %b %Y", "%a"),
    "hours": ("%a %d %b %Y %H:%S", "%H"),
}

interval_dateformat_map = {
    "years": ("%Y", "%Y"),
    "quarters": ("%b %Y", "%b %Y"),
    "months": ("%b %Y", "%b %Y"),
    "weeks": ("%W (%d %b %Y)", "%W"),
    "days": ("%a %d %b %Y", "%d %b %Y"),
    "hours": ("%a %d %b %Y %H:%S", "%H"),
}


def get_dateformat(interval: Interval, chart_type):
    if chart_type == "discreteBarChart":
        return interval_dateformat_map_bar_chart[interval.value]
    return interval_dateformat_map[interval.value]


def remove_multiple_keys(in_dict, entries_to_remove):
    for k in entries_to_remove:
        in_dict.pop(k, None)


class ChartDataView(TemplateView):
    template_name = "admin_tools_stats/chart_data.html"

    def get_context_data(self, *args, interval: Interval = None, graph_key=None, **kwargs):
        dashboard_stats = DashboardStats.objects.get(graph_key=graph_key)
        context = super().get_context_data(*args, **kwargs)

        if not (
            self.request.user.has_perm("admin_tools_stats.view_dashboardstats")
            or dashboard_stats.show_to_users
        ):
            context[
                "error"
            ] = "You have no permission to view this chart. Check if you are logged in"
            context["graph_title"] = dashboard_stats.graph_title
            return context

        configuration: Dict[str, Union[str, List[str]]] = self.request.GET.dict()
        remove_multiple_keys(configuration, ["csrfmiddlewaretoken", "_", "graph_key"])
        selected_interval: Interval = Interval(
            configuration.pop("select_box_interval", interval) or dashboard_stats.default_time_scale
        )
        operation = configuration.pop(
            "select_box_operation", dashboard_stats.type_operation_field_name
        )
        if not isinstance(operation, str):
            operation = None
        operation_field = configuration.pop(
            "select_box_operation_field", dashboard_stats.operation_field_name
        )
        if not isinstance(operation_field, str):
            operation_field = None
        context["chart_type"] = configuration.pop(
            "select_box_chart_type", dashboard_stats.default_chart_type
        )
        try:
            chart_tz = get_charts_timezone()
            time_since = datetime.strptime(str(configuration.pop("time_since")), "%Y-%m-%d")
            time_since = truncate(time_since, selected_interval.val())
            time_since = time_since.astimezone(chart_tz)

            time_until = datetime.strptime(str(configuration.pop("time_until")), "%Y-%m-%d")
            time_until = truncate_ceiling(time_until, selected_interval.val())
            time_until = time_until.astimezone(chart_tz)

            if time_since > time_until:
                context["error"] = "Time since is greater than time until"
                context["graph_title"] = dashboard_stats.graph_title
                return context

            if dashboard_stats.cache_values:
                get_time_series = dashboard_stats.get_multi_time_series_cached
            else:
                get_time_series = dashboard_stats.get_multi_time_series
            
            previous = get_dynamic_choices_array(configuration)
            def_filter = {}

            for p in previous:
                if p[1] != '':
                    id = p[0].replace('select_box_dynamic_', '')
                    crit = CriteriaToStatsM2M.objects.get(id=id)
                    def_filter["%s" % crit.get_dynamic_criteria_field_name()] = p[1]
            
            series = get_time_series(
                configuration,
                time_since,
                time_until,
                selected_interval,
                operation,
                operation_field,
                self.request.user,
                def_filter,
            )
        except Exception as e:
            if "debug" in configuration:
                raise e
            context["error"] = str(e)
            context["graph_title"] = dashboard_stats.graph_title
            logger.exception(e)
            return context
        criteria = dashboard_stats.get_multi_series_criteria(configuration)
        if criteria:
            choices = criteria.get_dynamic_choices(time_since, time_until, def_filter=def_filter)
        else:
            choices = {}

        ydata_serie: Dict[str, List[int]] = {}
        names = {}
        xdata = []
        total = 0
        serie_i_map: Dict[str, int] = OrderedDict()
        for date in sorted(
            series.keys(),
            key=lambda d: datetime(d.year, d.month, d.day, getattr(d, "hour", 0)),
        ):
            xdata.append(int(time.mktime(date.timetuple()) * 1000))
            for key, value in series[date].items():
                total += value if value else 0
                if key not in serie_i_map:
                    serie_i_map[key] = len(serie_i_map)
                y_key = "y%i" % serie_i_map[key]
                if y_key not in ydata_serie:
                    ydata_serie[y_key] = []
                    names["name%i" % serie_i_map[key]] = str(
                        choices[key][1] if key in choices else key
                    )
                ydata_serie[y_key].append(value if value else 0)

        context["extra"] = {
            "x_is_date": True,
            "tag_script_js": False,
        }

        if dashboard_stats.y_axis_format:
            context["extra"]["y_axis_format"] = dashboard_stats.y_axis_format

        if context["chart_type"] == "stackedAreaChart":
            context["extra"]["use_interactive_guideline"] = True

        tooltip_date_format, context["extra"]["x_axis_format"] = get_dateformat(
            selected_interval, context["chart_type"]
        )

        extra_serie = {
            "tooltip": {"y_start": "", "y_end": ""},
            "date_format": tooltip_date_format,
        }

        context["values"] = {
            "x": xdata,
            "name1": selected_interval,
            **ydata_serie,
            **names,
            "extra1": extra_serie,
        }
        
        context['extra']['show_controls'] = False
        context['extra']['show_legend'] = False

        context["chart_container"] = "chart_container_" + graph_key
        context["total"] = "%.0f" % total
        return context


class ChartsMixin:
    def get_charts_query(self):
        query = DashboardStats.objects.order_by("graph_title").all()
        if not self.request.user.has_perm("admin_tools_stats.view_dashboardstats"):
            query = query.filter(show_to_users=True)
        return query


class AnalyticsView(LoginRequiredMixin, ChartsMixin, TemplateView):
    def get_template_names(self):
        if self.request.user.has_perm("admin_tools_stats.view_dashboardstats"):
            return "admin_tools_stats/analytics.html"
        return "admin_tools_stats/analytics_user.html"

    def get_context_data(self, *args, **kwargs):
        context_data = super().get_context_data(*args, **kwargs)
        context_data["charts"] = self.get_charts_query()
        return context_data


class AnalyticsChartView(LoginRequiredMixin, ChartsMixin, TemplateView):
    template_name = "admin_tools_stats/analytics_chart.html"

    def get_context_data(self, *args, graph_key=None, **kwargs):
        context_data = super().get_context_data(*args, **kwargs)
        context_data["chart"] = self.get_charts_query().get(graph_key=graph_key)
        return context_data
