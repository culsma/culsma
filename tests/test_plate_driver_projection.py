"""Driver projections preserve the language's typed carrier target."""

import pytest

from culsma.domains.agitation import AgitationMode
from culsma.domains.labware import PlateReference
from culsma.driver.human import HumanDriver
from culsma.driver.robot import RobotDriver
from culsma.pipeline.plan_nodes import PlanStep


@pytest.mark.parametrize('driver_type', [HumanDriver, RobotDriver])
def test_plate_tap_reaches_driver_projection(driver_type):
    reference = PlateReference('carrier-instance', 'ReactionPlate', 8, 12).to_dict()
    action = PlanStep('tap', 'agit', {'mode': AgitationMode.TAP, 'sample': reference},
                      gate={'constraint': {'requirements': ['gentle']}})
    projection = driver_type().execute(action)
    assert projection.ok
    args = projection.payload['projection']['semantic_args']
    assert args['mode'] == 'tap'
    assert args['sample'] == reference
    if driver_type is RobotDriver:
        args['sample']['label'] = 'changed projection'
        assert reference['label'] is None
