"""Large-UI Driving Model page: profile selection, downloads and catalog actions.

Split out of runtime_app.StarShellSession, which calls these with itself as `session`.
"""

from openpilot.starpilot.ui.feature_settings_state import FeatureUiAction, feature_scroll
from openpilot.starpilot.ui.models_state import model_action_allowed, model_download_choices, model_profile_choices, model_profile_request
from openpilot.starpilot.ui.settings_state import Destination
from openpilot.starpilot.ui.shell import ShellMode


def models_ui(session, action: FeatureUiAction) -> None:
  if session._mode != ShellMode.SETTINGS or session.selected != Destination.DRIVING_MODEL:
    return
  state = session.model_snapshot()
  if action.kind == "back":
    session.selected = Destination.STAR
    session.model_scroll = 0
    session.input.cancel()
  elif action.kind == "scroll":
    session.model_scroll = feature_scroll(session.model_scroll, action.direction, len(state.rows))
  elif action.kind == "open" and action.row in state.rows and action.row.page in ("models:small", "models:big"):
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.system.ui.widgets import DialogResult
    from openpilot.system.ui.widgets.option_dialog import MultiOptionDialog
    profile = action.row.page.split(":", 1)[1]
    manager = session.model_manager_snapshot()
    choices = dict(model_profile_choices(manager, profile))
    if not choices:
      checking = any(m.get("checking") for m in manager.get("models", ()))
      session._unavailable("still checking installed models; try again" if checking else
                        "no installed Small model yet; use Download a model")
      return
    current = manager["activeSmallModel" if profile == "small" else "activeBigModel"]
    current_label = next((label for label, model_id in choices.items() if model_id == current), "")

    def confirmed(result):
      if result != DialogResult.CONFIRM or session._mode != ShellMode.SETTINGS or session.selected != Destination.DRIVING_MODEL:
        return
      fresh = session.model_manager_snapshot()
      if fresh["activeSmallModel" if profile == "small" else "activeBigModel"] != current:
        session._unavailable("saved model changed; reopen the selection")
        return
      request = model_profile_request(fresh, profile, choices.get(dialog.selection, ""))
      if request is not None:
        try:
          session.model_manager_action("active", request)
        except (OSError, ValueError, RuntimeError) as error:
          session._unavailable(str(error))
      session._snapshot_cache = None

    dialog = MultiOptionDialog(f"Active {'Small' if profile == 'small' else 'Big'}", list(choices), current_label, callback=confirmed)
    gui_app.push_widget(dialog)
  elif action.kind == "open" and action.row in state.rows and action.row.page == "models:download":
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.system.ui.widgets import DialogResult
    from openpilot.system.ui.widgets.option_dialog import MultiOptionDialog
    downloads = dict(model_download_choices(session.model_manager_snapshot()))
    if not downloads:
      session._unavailable("no model left to download")
      return

    def download(result):
      if result == DialogResult.CONFIRM and download_dialog.selection in downloads:
        model_download(session, "download", {"model": downloads[download_dialog.selection]})

    download_dialog = MultiOptionDialog("Download a model", list(downloads), "", callback=download)
    gui_app.push_widget(download_dialog)
  elif action.kind == "open" and action.row in state.rows and action.row.page in ("models:download_all", "models:cancel",
                                                                                 "models:refresh_manifest"):
    model_download(session, action.row.page.split(":", 1)[1], {})
  session._snapshot_cache = None

def model_download(session, action: str, payload: dict) -> None:
  if session._mode != ShellMode.SETTINGS or session.selected != Destination.DRIVING_MODEL:
    return
  fresh = session.model_manager_snapshot()
  model = next((m for m in fresh.get("models", ()) if m.get("value") == payload["model"]), None) if "model" in payload else None
  downloads = dict(model_download_choices(fresh)).values()
  if (not model_action_allowed(fresh, action, model) or action == "download" and (model or {}).get("value") not in downloads or
      action == "download_all" and not downloads):
    session._unavailable("turn off the vehicle, then try again")
  else:
    try:
      session.model_manager_action(action, payload)
    except (OSError, ValueError, RuntimeError) as error:
      session._unavailable(str(error))
  session._snapshot_cache = None
