"""Paged choice strip: window offset, arrow actions, and pinned editor geometry."""

from dataclasses import replace
import unittest

from openpilot.starpilot.ui.feature_settings_state import (
  SYSTEM_PRESETS, ChoiceStrip, FeatureInput, FeatureRow, FeatureSettingsState, FeatureUiAction,
  choice_strip_follow, choice_strip_initial, choice_strip_page,
  feature_row_top, value_buttons, value_editor_state, value_request,
)


def editor_for(choices, value, offset=None):
  row = FeatureRow("choice", "Choice", value, choices=choices, available=True)
  editor = value_editor_state(FeatureSettingsState(rows=(row,)), row.key)
  current = editor.rows[0]
  if offset is not None:
    editor = replace(editor, choice_offset=offset)
  return editor, current


def buttons(editor, row):
  return value_buttons(editor, row, feature_row_top(editor))


def named(editor, row, name):
  return next(button for button in buttons(editor, row) if button[0] == name)


def tap(editor, bounds):
  x, y, width, height = bounds
  return FeatureInput.target(x + width / 2, y + height / 2, editor)


class ChoiceStripTests(unittest.TestCase):
  def test_opening_a_four_choice_editor_centers_the_current_value(self):
    choices = tuple(f"Choice {i}" for i in range(4))
    editor, row = editor_for(choices, choices[2])
    self.assertEqual(editor.choice_offset, 1)
    self.assertEqual([name for name, _, _ in buttons(editor, row)], ["-", "<", *choices[1:4], ">", "+"])
    self.assertTrue(named(editor, row, "<")[2])
    self.assertFalse(named(editor, row, ">")[2])
    self.assertIsNone(tap(editor, named(editor, row, ">")[1]))

  def test_arrows_page_by_three_and_clamp_at_full_pages(self):
    choices = tuple(f"Choice {i}" for i in range(15))
    editor, row = editor_for(choices, choices[0])
    self.assertEqual(editor.choice_offset, 0)
    self.assertFalse(named(editor, row, "<")[2])
    self.assertIsNone(tap(editor, named(editor, row, "<")[1]))
    offset = editor.choice_offset
    for expected in (3, 6, 9):
      editor = replace(editor, choice_offset=offset)
      self.assertEqual(tap(editor, named(editor, row, ">")[1]), FeatureUiAction("page", row, 1))
      offset = choice_strip_page(row, offset + 3)
      self.assertEqual(offset, expected)
    editor = replace(editor, choice_offset=offset)
    self.assertTrue(named(editor, row, ">")[2])
    self.assertEqual(tap(editor, named(editor, row, ">")[1]), FeatureUiAction("page", row, 1))
    offset = choice_strip_page(row, offset + 3)
    self.assertEqual(offset, 12)
    editor = replace(editor, choice_offset=offset)
    self.assertFalse(named(editor, row, ">")[2])
    self.assertIsNone(tap(editor, named(editor, row, ">")[1]))
    self.assertEqual(choice_strip_page(row, offset + 3), 12)
    editor = replace(editor, choice_offset=12)
    self.assertEqual([name for name, _, _ in buttons(editor, row)], ["-", "<", *choices[12:15], ">", "+"])
    self.assertEqual(tap(editor, named(editor, row, "<")[1]), FeatureUiAction("page", row, -1))
    offset = choice_strip_page(row, 12 - 3)
    self.assertEqual(offset, 9)
    editor = replace(editor, choice_offset=9)
    self.assertEqual([name for name, _, _ in buttons(editor, row)], ["-", "<", *choices[9:12], ">", "+"])

  def test_visible_choice_taps_select_the_windowed_choice(self):
    choices = tuple(f"Choice {i}" for i in range(7))
    editor, row = editor_for(choices, choices[0], offset=3)
    visible = buttons(editor, row)
    self.assertEqual([name for name, _, _ in visible], ["-", "<", *choices[3:6], ">", "+"])
    action = tap(editor, visible[3][1])  # the 2nd visible choice button
    self.assertEqual(action, FeatureUiAction("action", row, 3))
    request = value_request(editor, action)
    self.assertEqual(request.value, choices[4])

  def test_arrow_taps_change_nothing(self):
    choices = tuple(f"Choice {i}" for i in range(7))
    editor, row = editor_for(choices, choices[3], offset=1)
    for name, direction in (("<", -1), (">", 1)):
      action = tap(editor, named(editor, row, name)[1])
      self.assertEqual(action, FeatureUiAction("page", row, direction))
      self.assertIsNone(value_request(editor, action))
    self.assertEqual(value_request(editor, FeatureUiAction("page", row, 1)), None)
    self.assertEqual(value_request(editor, FeatureUiAction("page", row, -1)), None)
    self.assertEqual(row.value, choices[3])

  def test_steps_follow_the_window_only_when_the_value_leaves_it(self):
    choices = tuple(f"Choice {i}" for i in range(7))
    editor, row = editor_for(choices, choices[0])
    offset = editor.choice_offset
    current = choices[0]
    for _ in range(2):
      state = replace(editor, rows=(replace(row, value=current),))
      request = value_request(state, FeatureUiAction("change", state.rows[0], 1))
      self.assertEqual(request.value, choices[choices.index(current) + 1])
      current = request.value
      offset = choice_strip_follow(replace(row, value=current), offset)
    self.assertEqual(offset, 0)
    state = replace(editor, rows=(replace(row, value=current),))
    request = value_request(state, FeatureUiAction("change", state.rows[0], 1))
    self.assertEqual(request.value, choices[3])
    offset = choice_strip_follow(replace(row, value=request.value), offset)
    self.assertEqual(offset, 1)
    editor = replace(editor, choice_offset=offset)
    self.assertIn(choices[3], [name for name, _, _ in buttons(editor, row)])

  def test_opening_window_is_clamped_for_first_and_last_values(self):
    choices = tuple(f"Choice {i}" for i in range(15))
    self.assertEqual(choice_strip_initial(FeatureRow("c", "C", choices[0], choices=choices)), 0)
    self.assertEqual(choice_strip_initial(FeatureRow("c", "C", choices[1], choices=choices)), 0)
    self.assertEqual(choice_strip_initial(FeatureRow("c", "C", choices[14], choices=choices)), 12)
    self.assertEqual(choice_strip_initial(FeatureRow("c", "C", "Not saved", choices=choices)), 0)

  def test_three_or_fewer_choices_keep_the_original_geometry(self):
    two = FeatureRow("two", "Two", "A", choices=("A", "B"), available=True)
    editor = replace(value_editor_state(FeatureSettingsState(rows=(two,)), "two"), choice_offset=5)
    self.assertEqual(choice_strip_page(two, 5), 0)
    self.assertEqual(value_buttons(editor, editor.rows[0], 0), (
      ("-", (575.0, 110.0, 200.0, 200.0), False),
      ("A", (575.0, 356.0, 747.5, 200.0), False),
      ("B", (1346.5, 356.0, 747.5, 200.0), True),
      ("+", (1894.0, 110.0, 200.0, 200.0), True),
    ))
    three = FeatureRow("three", "Three", "B", choices=("A", "B", "C"), available=True)
    editor = replace(value_editor_state(FeatureSettingsState(rows=(three,)), "three"), choice_offset=5)
    self.assertEqual(value_buttons(editor, editor.rows[0], 0), (
      ("-", (575.0, 110.0, 200.0, 200.0), True),
      ("A", (575.0, 356.0, 490.3333333333333, 200.0), True),
      ("B", (1089.3333333333333, 356.0, 490.3333333333333, 200.0), False),
      ("C", (1603.6666666666665, 356.0, 490.3333333333333, 200.0), True),
      ("+", (1894.0, 110.0, 200.0, 200.0), True),
    ))

  def test_paged_geometry_puts_arrows_at_the_strip_ends(self):
    four = FeatureRow("four", "Four", "A", choices=("A", "B", "C", "D"), available=True)
    editor = replace(value_editor_state(FeatureSettingsState(rows=(four,)), "four"), choice_offset=0)
    self.assertEqual(value_buttons(editor, editor.rows[0], 0), (
      ("-", (575.0, 110.0, 200.0, 200.0), False),
      ("<", (575.0, 356.0, 120.0, 200.0), False),
      ("A", (719.0, 356.0, 394.3333333333333, 200.0), False),
      ("B", (1137.3333333333333, 356.0, 394.3333333333333, 200.0), True),
      ("C", (1555.6666666666665, 356.0, 394.3333333333333, 200.0), True),
      (">", (1974.0, 356.0, 120.0, 200.0), True),
      ("+", (1894.0, 110.0, 200.0, 200.0), True),
    ))

  def test_explicit_preset_rows_keep_one_button_per_preset(self):
    # Screen and power rows supply their own short preset set; it is not the row's choice list, so it is never paged.
    for key, value in (("power:hours", "6 h"), ("power:volts", "12.0 V"), ("ScreenBrightness", "50")):
      with self.subTest(key=key):
        presets = SYSTEM_PRESETS[key]
        row = FeatureRow(key, "Preset row", value, choices=tuple(f"choice {i}" for i in range(30)), presets=presets, available=True)
        editor = FeatureSettingsState(rows=(row,), editor=True, choice_offset=3)
        names = [name for name, _, _ in buttons(editor, row)]
        self.assertEqual(names, ["-", *(preset for preset, _ in presets), "+"])
        self.assertEqual(choice_strip_page(row, 3), 0)
        self.assertEqual(choice_strip_initial(row), 0)

  def test_numeric_rows_keep_the_original_geometry(self):
    number = FeatureRow("number", "Number", "50", step=5, minimum=0.0, maximum=100.0, available=True, default_value="25")
    editor = replace(value_editor_state(FeatureSettingsState(rows=(number,)), "number"), choice_offset=5)
    row = editor.rows[0]
    self.assertEqual(tuple(value for value, _ in row.presets), ("0.0", "25.0", "100.0"))
    self.assertEqual(value_buttons(editor, row, 0), (
      ("-", (575.0, 110.0, 200.0, 200.0), True),
      ("0.0", (575.0, 356.0, 490.3333333333333, 200.0), True),
      ("25.0", (1089.3333333333333, 356.0, 490.3333333333333, 200.0), True),
      ("100.0", (1603.6666666666665, 356.0, 490.3333333333333, 200.0), True),
      ("+", (1894.0, 110.0, 200.0, 200.0), True),
    ))


class ChoiceStripTrackerTest(unittest.TestCase):
  CHOICES = tuple(f"c{index}" for index in range(15))

  def shown(self, strip, value, area="feature", key="choice"):
    row = FeatureRow(key, "Choice", value, choices=self.CHOICES, available=True)
    state = strip.window(area, value_editor_state(FeatureSettingsState(rows=(row,)), key))
    return state, state.rows[0]

  def test_open_places_the_window_and_arrows_move_it_without_touching_the_value(self):
    strip = ChoiceStrip()
    state, row = self.shown(strip, "c7")
    self.assertEqual(state.choice_offset, 6)
    action = tap(state, named(state, row, ">")[1])
    self.assertEqual(action, FeatureUiAction("page", row, 1))
    strip.page(action)
    state, row = self.shown(strip, "c7")
    self.assertEqual((state.choice_offset, row.value), (9, "c7"))
    strip.page(FeatureUiAction("page", row, 1))
    strip.page(FeatureUiAction("page", row, 1))
    self.assertEqual(self.shown(strip, "c7")[0].choice_offset, 12)
    strip.page(FeatureUiAction("page", row, -1))
    self.assertEqual(self.shown(strip, "c7")[0].choice_offset, 9)

  def test_window_follows_a_changed_value_only_as_far_as_needed(self):
    strip = ChoiceStrip()
    self.assertEqual(self.shown(strip, "c7")[0].choice_offset, 6)
    self.assertEqual(self.shown(strip, "c8")[0].choice_offset, 6)
    self.assertEqual(self.shown(strip, "c9")[0].choice_offset, 7)
    self.assertEqual(self.shown(strip, "c5")[0].choice_offset, 5)

  def test_closing_the_editor_forgets_a_paged_window(self):
    strip = ChoiceStrip()
    state, row = self.shown(strip, "c7")
    strip.page(FeatureUiAction("page", row, -1))
    self.assertEqual(self.shown(strip, "c7")[0].choice_offset, 3)
    overview = FeatureSettingsState(rows=(row, replace(row, key="other")))
    self.assertIs(strip.window("feature", overview), overview)
    self.assertEqual(self.shown(strip, "c7")[0].choice_offset, 6)

  def test_another_row_or_area_gets_its_own_window(self):
    strip = ChoiceStrip()
    state, row = self.shown(strip, "c7")
    strip.page(FeatureUiAction("page", row, 1))
    self.assertEqual(self.shown(strip, "c1", area="sounds", key="other")[0].choice_offset, 0)
    self.assertEqual(self.shown(strip, "c7")[0].choice_offset, 9)
    self.assertEqual(self.shown(strip, "c1", key="other")[0].choice_offset, 0)

  def test_rows_that_do_not_page_stay_at_zero(self):
    strip = ChoiceStrip()
    row = FeatureRow("three", "Three", "b", choices=("a", "b", "c"), available=True)
    state = strip.window("feature", value_editor_state(FeatureSettingsState(rows=(row,)), "three"))
    strip.page(FeatureUiAction("page", state.rows[0], 1))
    self.assertEqual(strip.window("feature", state).choice_offset, 0)


if __name__ == "__main__":
  unittest.main()
