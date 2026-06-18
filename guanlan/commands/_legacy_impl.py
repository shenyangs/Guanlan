# -*- coding: utf-8 -*-
"""Compatibility re-exports for split Guanlan CLI command handlers."""

from guanlan.commands._feedback import (
    _auto_feedback_enabled,
    _auto_feedback_for_research,
    _auto_feedback_for_search,
    _is_agent_runtime,
    _normalized_bool,
    _submit_auto_feedback,
)
from guanlan.commands._ops_helpers import (
    _classify_github_response_error,
    _classify_update_error,
    _github_get_with_retry,
    _parse_twitter_cookie_input,
    _print_background_update_notice_if_available,
    _print_sensitive_access_notice,
    _print_update_notice_if_available,
    _should_show_background_update_notice,
    _update_error_text,
)
from guanlan.commands.admin import (
    _cmd_archive,
    _cmd_capabilities,
    _cmd_check_update,
    _cmd_configure,
    _cmd_doctor,
    _cmd_eval,
    _cmd_format,
    _cmd_health_watch,
    _cmd_install,
    _cmd_mcp,
    _cmd_plugin,
    _cmd_profile,
    _cmd_quality,
    _cmd_report,
    _cmd_serve,
    _cmd_setup,
    _cmd_skill,
    _cmd_status,
    _cmd_stock,
    _cmd_uninstall,
    _cmd_welcome,
    _configure_xhs_cookies,
    _detect_environment,
    _install_bili_deps,
    _install_browser_use_deps,
    _install_mcporter,
    _install_mcporter_safe,
    _install_opencli_deps,
    _install_openguanlan_deps,
    _install_reddit_deps,
    _install_skill,
    _install_system_deps,
    _install_system_deps_dryrun,
    _install_system_deps_safe,
    _install_twitter_deps,
    _install_wechat_deps,
    _install_weibo_deps,
    _install_xhs_deps,
    _install_xiaoyuzhou_deps,
    _install_zsxq_deps,
    _uninstall_skill,
)
from guanlan.commands.feeds import (
    _cmd_feeds,
    _cmd_pulse,
)
from guanlan.commands.hotnews import (
    _cmd_hotnews,
)
from guanlan.commands.read import (
    _cmd_browser_assist,
    _cmd_diagnose,
    _cmd_read,
    _cmd_wechat_exporter,
    _format_browser_assist_session_markdown,
    _format_wechat_exporter_records_markdown,
    _format_wechat_exporter_status_markdown,
    _read_quality_kwargs,
)
from guanlan.commands.research import (
    _cmd_compare,
    _cmd_dossier,
    _cmd_feedback,
    _cmd_investigate,
    _cmd_prompt,
    _cmd_recipe,
    _cmd_research,
    _cmd_sources,
    _cmd_timeline,
    _cmd_yinshen,
)
from guanlan.commands.search import (
    _cmd_agent,
    _cmd_route,
    _cmd_search,
    _cmd_workflow,
)
from guanlan.commands.watch import (
    _cmd_watch_intents,
)

__all__ = ['_print_sensitive_access_notice', '_parse_twitter_cookie_input', '_classify_update_error', '_update_error_text', '_classify_github_response_error', '_github_get_with_retry', '_print_update_notice_if_available', '_should_show_background_update_notice', '_print_background_update_notice_if_available', '_normalized_bool', '_is_agent_runtime', '_auto_feedback_enabled', '_submit_auto_feedback', '_auto_feedback_for_search', '_auto_feedback_for_research', '_cmd_feedback', '_cmd_route', '_cmd_workflow', '_cmd_agent', '_cmd_search', '_cmd_hotnews', '_cmd_pulse', '_cmd_feeds', '_cmd_watch_intents', '_cmd_diagnose', '_cmd_browser_assist', '_cmd_wechat_exporter', '_format_wechat_exporter_status_markdown', '_format_wechat_exporter_records_markdown', '_format_browser_assist_session_markdown', '_cmd_read', '_read_quality_kwargs', '_cmd_research', '_cmd_investigate', '_cmd_recipe', '_cmd_sources', '_cmd_compare', '_cmd_timeline', '_cmd_dossier', '_cmd_yinshen', '_cmd_prompt', '_cmd_welcome', '_cmd_capabilities', '_cmd_stock', '_cmd_install', '_install_skill', '_uninstall_skill', '_cmd_skill', '_cmd_format', '_cmd_archive', '_cmd_mcp', '_cmd_serve', '_cmd_plugin', '_cmd_eval', '_cmd_quality', '_install_system_deps', '_install_xiaoyuzhou_deps', '_install_twitter_deps', '_install_browser_use_deps', '_install_opencli_deps', '_install_openguanlan_deps', '_install_xhs_deps', '_install_zsxq_deps', '_install_reddit_deps', '_install_bili_deps', '_install_weibo_deps', '_install_wechat_deps', '_install_system_deps_safe', '_install_system_deps_dryrun', '_install_mcporter', '_install_mcporter_safe', '_detect_environment', '_cmd_configure', '_configure_xhs_cookies', '_cmd_uninstall', '_cmd_doctor', '_cmd_profile', '_cmd_setup', '_cmd_check_update', '_cmd_health_watch', '_cmd_status', '_cmd_report']
