"""Lane guidance (Navigation.Lane text arrows) and the "toward" line for the head unit's dash map (display only).

Adapted from the fork's test_route_lanes.py: PTM keeps Text lane directions, so the fork's bitmask, intersection-lane,
merge-arrow and unpainted-lane cases are not ported.

The steps follow the Mapbox Directions v5 format: banner `sub` lane components and the maneuver's
intersection `lanes` (docs.mapbox.com/api/navigation/directions, "Lane object" and "Banner instruction object").
"""
import copy

from openpilot.starpilot.navigation.route_engine import NavigationRoute, toward

# I-75 north, 1.1 km before exit 34 on the right: four lanes, the two right ones go to the exit
HIGHWAY = [
  {'distance': 1112., 'duration': 40., 'name': 'North Central Expressway', 'ref': 'US 75',
   'maneuver': {'type': 'depart', 'location': [0., 0.]},
   'bannerInstructions': [
     {'distanceAlongGeometry': 1112., 'primary': {'text': 'Exit 34 I 635 East', 'type': 'off ramp', 'modifier': 'slight right'},
      'secondary': {'text': 'Garland', 'components': [{'text': 'Garland', 'type': 'text'}]}},
     {'distanceAlongGeometry': 400., 'primary': {'text': 'Exit 34 I 635 East', 'type': 'off ramp', 'modifier': 'slight right'},
      'secondary': {'text': 'Garland', 'components': [{'text': 'Garland', 'type': 'text'}]},
      'sub': {'text': '', 'components': [
        {'type': 'lane', 'text': '', 'directions': ['straight'], 'active': False},
        {'type': 'lane', 'text': '', 'directions': ['straight'], 'active': False},
        {'type': 'lane', 'text': '', 'directions': ['straight', 'slight right'], 'active': True, 'active_direction': 'slight right'},
        {'type': 'lane', 'text': '', 'directions': ['slight right'], 'active': True, 'active_direction': 'slight right'}]}}]},
  {'distance': 0., 'duration': 0., 'name': 'I 635', 'destinations': 'I 635 East: Garland',
   'maneuver': {'type': 'off ramp', 'modifier': 'slight right', 'location': [.01, 0.]},
   'intersections': [{'location': [.01, 0.], 'lanes': [
     {'valid': False, 'active': False, 'indications': ['straight']},
     {'valid': True, 'active': True, 'indications': ['slight right'], 'valid_indication': 'slight right'}]}]},
]
GEOMETRY = {'distance': 1112., 'duration': 40., 'geometry': {'coordinates': [[0., 0.], [.01, 0.]]}}


def instruction(steps):
  return NavigationRoute({**GEOMETRY, 'legs': [{'steps': steps}]}).progress((.005, 0.), 25., 90.).instruction


def test_the_banner_lanes_reach_the_instruction_left_to_right_as_text():
  result = instruction(copy.deepcopy(HIGHWAY))
  assert result['lanes'] == [
    {'directions': ['straight'], 'active': False, 'activeDirection': ''},
    {'directions': ['straight'], 'active': False, 'activeDirection': ''},
    {'directions': ['straight', 'slight right'], 'active': True, 'activeDirection': 'slight right'},
    {'directions': ['slight right'], 'active': True, 'activeDirection': 'slight right'}]
  assert result['toward'] == 'Garland'


def test_no_banner_lanes_means_none_sent():
  steps = copy.deepcopy(HIGHWAY)
  del steps[0]['bannerInstructions'][1]['sub']
  assert instruction(steps)['lanes'] == []
  assert instruction(steps)['toward'] == 'Garland'


def test_toward_comes_from_the_banner_else_the_destinations():
  assert toward([{'secondary': {'text': '  Garland  Mesquite '}}], {}, 'I 635 East') == 'Garland Mesquite'
  assert toward([{}], {'destinations': 'I 635 East: Garland, Mesquite'}, 'I 635 East') == 'Garland, Mesquite'
  assert toward([], {'destinations': 'Downtown'}, 'Exit 3') == 'Downtown'
  assert toward([], {}, 'Main Street') == ''
  # already in the instruction: not repeated
  assert toward([{'secondary': {'text': 'Garland'}}], {}, 'Exit 34 toward Garland') == ''
  assert toward([{'secondary': {'text': 'Garland'}}], {}, 'Garland Road') == ''
  assert len(toward([{'secondary': {'text': 'x' * 200}}], {}, '')) == 80


def test_the_arrive_step_has_no_destination():
  steps = copy.deepcopy(HIGHWAY)
  steps[1]['bannerInstructions'] = copy.deepcopy(steps[0]['bannerInstructions'])
  route = NavigationRoute({**GEOMETRY, 'legs': [{'steps': steps}]})
  assert route.steps[-1].toward == ''
  assert route.steps[0].lanes and route.steps[0].toward == 'Garland'


def test_the_lanes_fit_the_navigation_message():
  from openpilot.cereal import messaging
  from openpilot.starpilot.navigation.wire import navigation_envelope
  message = messaging.new_message('starpilotNavigation', valid=True)
  message.starpilotNavigation = navigation_envelope({'instruction': instruction(copy.deepcopy(HIGHWAY))})
  sent = message.starpilotNavigation.navigation.instruction
  assert [(list(lane.directions), lane.active, lane.activeDirection) for lane in sent.lanes] == [
    (['straight'], False, ''), (['straight'], False, ''), (['straight', 'slight right'], True, 'slight right'),
    (['slight right'], True, 'slight right')]
  assert sent.toward == 'Garland'
