"""The map overlay is created only when the AA layout enables it, prepared outside the frame, drawn at its placement."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from openpilot.starpilot.system.starport import projection_onroad as projection
from openpilot.starpilot.system.starport.projection_layout import default_layout_for_viewport
from openpilot.starpilot.system.starport.tests import test_projection_onroad_boundary as boundary


class FakeMap:
  def __init__(self, *, fonts):
    self.fonts = fonts
    self.prepared, self.drawn, self.closed = [], [], False

  def prepare(self, data, width, height):
    self.prepared.append((data, width, height))

  def draw(self, rect, opacity):
    self.drawn.append((rect, opacity))

  def close(self):
    self.closed = True


class FakeFeed:
  navigating = False  # what the feed reports: the overlay exists only while this is True

  def __init__(self):
    self.reads = []
    self.destinations = []

  def read(self, sm, *, navigation_requested=None, destination=None):
    self.reads.append(sm)
    self.destinations.append(destination)
    return SimpleNamespace(label="map input", navigation_active=self.navigating, route=())


def navigate(view, value):
  feed = view.map_feed
  assert feed is not None
  feed.navigating = value


class FakeLease:
  def __init__(self):
    self.touches, self.releases = 0, 0

  def touch(self):
    self.touches += 1

  def release(self):
    self.releases += 1


class TestProjectionMap(unittest.TestCase):
  def setUp(self):
    self.lease = FakeLease()
    patcher = patch.object(projection, 'MapLeaseWriter', return_value=self.lease)
    patcher.start()
    self.addCleanup(patcher.stop)

  def native(self):
    native, events = boundary.TestProjectionOnroad().dependencies()
    native.map_overlay, native.map_feed = FakeMap, FakeFeed
    return native, events

  def layout(self, **map_placement):
    document = default_layout_for_viewport((2880, 1080))
    document["widgets"]["nav_map"].update(map_placement)
    return document

  def test_disabled_map_builds_nothing(self):
    native, _ = self.native()
    view = projection.ProjectionOnroad(dependencies=native, viewport=(2880, 1080), customization=self.layout())
    self.assertIsNone(view.map)
    self.assertIsNone(view.map_feed)
    view.prepare()
    view.close()

  def test_enabled_map_feed_is_warm_but_the_overlay_waits_for_navigation(self):
    native, _ = self.native()
    layout = self.layout(enabled=True, x=100, y=200, width=640, height=480, opacity=45)
    view = projection.ProjectionOnroad(dependencies=native, viewport=(2880, 1080), customization=layout)
    self.assertIsInstance(view.map_feed, FakeFeed)
    self.assertIsNone(view.map, "the tile thread and canvases are not built until navigation starts")
    view.prepare()
    self.assertEqual(view.map_feed.reads, [], "nothing to read while offroad")
    native.ui_state.started = True
    view.prepare()
    self.assertEqual(view.map_feed.reads, [native.ui_state.sm])
    self.assertEqual(self.lease.touches, 1, "the lease is held whenever the layout places the map")
    self.assertIsNone(view.map)
    self.assertIsNone(view.onroad.map_layer)
    navigate(view, True)
    view.prepare()
    self.assertIsInstance(view.map, FakeMap)
    self.assertIs(view.map.fonts, view.fonts)
    self.assertEqual(view.onroad.map_layer, view._map_layer)
    self.assertEqual([(data.label, width, height) for data, width, height in view.map.prepared], [("map input", 640, 480)])
    self.assertEqual(view.map_feed.reads, [native.ui_state.sm, native.ui_state.sm])
    self.assertEqual(view.map_feed.destinations, [None, None], "no favorites: the feed keeps navigation's own name")
    view._map_layer(None, None)
    self.assertEqual(view.map.drawn, [((100, 200, 640, 480), 0.45)])
    overlay = view.map
    view.close()
    self.assertTrue(overlay.closed)

  def test_overlay_is_freed_only_after_navigation_has_been_off_for_the_hold(self):
    native, _ = self.native()
    view = projection.ProjectionOnroad(dependencies=native, viewport=(2880, 1080), customization=self.layout(enabled=True))
    self.addCleanup(view.close)
    native.ui_state.started = True
    navigate(view, True)
    clock = [1_000_000_000]
    with patch.object(projection.time, 'monotonic_ns', side_effect=lambda: clock[0]):
      view.prepare()
      overlay = view.map
      self.assertIsInstance(overlay, FakeMap)
      navigate(view, False)
      view.prepare()
      clock[0] += projection.MAP_RELEASE_AFTER_NAVIGATION_NS - 1
      view.prepare()
      self.assertIs(view.map, overlay, "a brief gap in the navigation state keeps the map")
      self.assertFalse(overlay.closed)
      navigate(view, True)
      view.prepare()
      clock[0] += projection.MAP_RELEASE_AFTER_NAVIGATION_NS
      view.prepare()
      self.assertIs(view.map, overlay, "navigation coming back restarts the hold")
      navigate(view, False)
      view.prepare()
      clock[0] += projection.MAP_RELEASE_AFTER_NAVIGATION_NS
      view.prepare()
    self.assertTrue(overlay.closed)
    self.assertIsNone(view.map)
    self.assertIsNone(view.onroad.map_layer)
    self.assertIsNotNone(view.map_feed, "the feed stays warm for the next route")

  def test_older_dependencies_without_a_map_still_work(self):
    native, _ = self.native()
    del native.map_overlay
    view = projection.ProjectionOnroad(dependencies=native, viewport=(2880, 1080),
                                       customization=self.layout(enabled=True))
    self.assertIsNone(view.map)
    self.assertIsNone(view.map_feed)
    native.ui_state.started = True
    view.prepare()
    view.close()

  def test_layout_document_is_not_mutated(self):
    native, _ = self.native()
    layout = self.layout(enabled=True)
    before = copy.deepcopy(layout)
    view = projection.ProjectionOnroad(dependencies=native, viewport=(2880, 1080), customization=layout)
    native.ui_state.started = True
    view.prepare()
    view.close()
    self.assertEqual(layout, before)

  def test_turning_the_map_off_frees_it_and_the_lease_until_it_returns(self):
    native, _ = self.native()
    layout = self.layout(enabled=True)
    view = projection.ProjectionOnroad(dependencies=native, viewport=(2880, 1080), customization=layout)
    native.ui_state.started = True
    navigate(view, True)
    view.prepare()
    self.assertEqual(self.lease.touches, 1)
    overlay = view.map
    self.assertIsInstance(overlay, FakeMap)
    off = copy.deepcopy(layout)
    off["widgets"]["nav_map"]["enabled"] = False
    view.apply_layout(off)
    view.prepare()
    self.assertTrue(overlay.closed)
    self.assertIsNone(view.map)
    self.assertIsNone(view.onroad.map_layer)
    self.assertGreaterEqual(self.lease.releases, 1)
    self.assertIsNone(view.map_feed)
    view.apply_layout(layout)
    self.assertIsInstance(view.map_feed, FakeFeed)
    navigate(view, True)
    view.prepare()
    self.assertIsInstance(view.map, FakeMap)
    self.assertIsNot(view.map, overlay)
    view.close()
