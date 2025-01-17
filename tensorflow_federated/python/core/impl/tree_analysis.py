# Lint as: python3
# Copyright 2019, The TensorFlow Federated Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""A library of static analysis functions that can be applied to ASTs."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from tensorflow_federated.python.common_libs import py_typecheck
from tensorflow_federated.python.core.api import computation_types
from tensorflow_federated.python.core.impl import computation_building_blocks
from tensorflow_federated.python.core.impl import intrinsic_defs
from tensorflow_federated.python.core.impl import placement_literals
from tensorflow_federated.python.core.impl import transformation_utils


def count_types(comp, types):
  return count(comp, lambda x: isinstance(x, types))


def count(comp, predicate=None):
  """Returns the number of computations in `comp` matching `predicate`.

  Args:
    comp: The computation to test.
    predicate: An optional Python function that takes a computation as a
      parameter and returns a boolean value. If `None`, all computations are
      counted.
  """
  py_typecheck.check_type(comp,
                          computation_building_blocks.ComputationBuildingBlock)
  counter = [0]

  def _function(comp):
    if predicate is None or predicate(comp):
      counter[0] += 1
    return comp, False

  transformation_utils.transform_postorder(comp, _function)
  return counter[0]


def check_has_single_placement(comp, single_placement):
  """Checks that the AST of `comp` contains only `single_placement`.

  Args:
    comp: Instance of `computation_building_blocks.ComputationBuildingBlock`.
    single_placement: Instance of `placement_literals.PlacementLiteral` which
      should be the only placement present under `comp`.

  Raises:
    ValueError: If the AST under `comp` contains any
    `computation_types.FederatedType` other than `single_placement`.
  """
  py_typecheck.check_type(comp,
                          computation_building_blocks.ComputationBuildingBlock)
  py_typecheck.check_type(single_placement, placement_literals.PlacementLiteral)

  def _check_single_placement(comp):
    """Checks that the placement in `type_spec` matches `single_placement`."""
    if (isinstance(comp.type_signature, computation_types.FederatedType) and
        comp.type_signature.placement != single_placement):
      raise ValueError(
          'Comp contains a placement other than {}; '
          'placement {} on comp {} inside the structure. '.format(
              single_placement, comp.type_signature.placement,
              computation_building_blocks.compact_representation(comp)))
    return comp, False

  transformation_utils.transform_postorder(comp, _check_single_placement)


def check_intrinsics_whitelisted_for_reduction(comp):
  """Checks whitelist of intrinsics reducible to aggregate or broadcast.

  Args:
    comp: Instance of `computation_building_blocks.ComputationBuildingBlock` to
      check for presence of intrinsics not currently immediately reducible to
      `FEDERATED_AGGREGATE` or `FEDERATED_BROADCAST`, or local processing.

  Raises:
    ValueError: If we encounter an intrinsic under `comp` that is not
    whitelisted as currently reducible.
  """
  # TODO(b/135930668): Factor this and other non-transforms (e.g.
  # `check_has_unique_names` out of this file into a structure specified for
  # static analysis of ASTs.
  py_typecheck.check_type(comp,
                          computation_building_blocks.ComputationBuildingBlock)
  uri_whitelist = (
      intrinsic_defs.FEDERATED_AGGREGATE.uri,
      intrinsic_defs.FEDERATED_APPLY.uri,
      intrinsic_defs.FEDERATED_BROADCAST.uri,
      intrinsic_defs.FEDERATED_MAP.uri,
      intrinsic_defs.FEDERATED_MAP_ALL_EQUAL.uri,
      intrinsic_defs.FEDERATED_VALUE_AT_CLIENTS.uri,
      intrinsic_defs.FEDERATED_VALUE_AT_SERVER.uri,
      intrinsic_defs.FEDERATED_ZIP_AT_SERVER.uri,
      intrinsic_defs.FEDERATED_ZIP_AT_CLIENTS.uri,
  )

  def _check_whitelisted(comp):
    if isinstance(comp, computation_building_blocks.Intrinsic
                 ) and comp.uri not in uri_whitelist:
      raise ValueError(
          'Encountered an Intrinsic not currently reducible to aggregate or '
          'broadcast, the intrinsic {}'.format(
              computation_building_blocks.compact_representation(comp)))
    return comp, False

  transformation_utils.transform_postorder(comp, _check_whitelisted)


def check_has_unique_names(comp):
  if not transformation_utils.has_unique_names(comp):
    raise ValueError(
        'This transform should only be called after we have uniquified all '
        '`computation_building_blocks.Reference` names, since we may be moving '
        'computations with unbound references under constructs which bind '
        'those references.')
