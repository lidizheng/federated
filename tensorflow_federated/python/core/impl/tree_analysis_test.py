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
"""Tests for tree_analysis."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from absl.testing import absltest

import tensorflow as tf

from tensorflow_federated.python.core.api import computation_types
from tensorflow_federated.python.core.api import placements
from tensorflow_federated.python.core.impl import computation_building_blocks
from tensorflow_federated.python.core.impl import computation_constructing_utils
from tensorflow_federated.python.core.impl import computation_test_utils
from tensorflow_federated.python.core.impl import intrinsic_defs
from tensorflow_federated.python.core.impl import tree_analysis


class IntrinsicsWhitelistedTest(absltest.TestCase):

  def test_raises_on_none(self):
    with self.assertRaises(TypeError):
      tree_analysis.check_intrinsics_whitelisted_for_reduction(None)

  def test_passes_with_federated_map(self):
    intrinsic = computation_building_blocks.Intrinsic(
        intrinsic_defs.FEDERATED_MAP.uri,
        computation_types.FunctionType([
            computation_types.FunctionType(tf.int32, tf.float32),
            computation_types.FederatedType(tf.int32, placements.CLIENTS)
        ], computation_types.FederatedType(tf.float32, placements.CLIENTS)))
    tree_analysis.check_intrinsics_whitelisted_for_reduction(intrinsic)

  def test_raises_with_federated_mean(self):
    intrinsic = computation_building_blocks.Intrinsic(
        intrinsic_defs.FEDERATED_MEAN.uri,
        computation_types.FunctionType(
            computation_types.FederatedType(tf.int32, placements.CLIENTS),
            computation_types.FederatedType(tf.int32, placements.SERVER)))

    with self.assertRaisesRegex(
        ValueError,
        computation_building_blocks.compact_representation(intrinsic)):
      tree_analysis.check_intrinsics_whitelisted_for_reduction(intrinsic)


def dummy_intrinsic_predicate(x):
  return isinstance(
      x, computation_building_blocks.Intrinsic) and x.uri == 'dummy_intrinsic'


class NodesDependentOnPredicateTest(absltest.TestCase):

  def test_raises_on_none_comp(self):
    with self.assertRaises(TypeError):
      tree_analysis.extract_nodes_dependent_on_predicate(None, lambda x: True)

  def test_raises_on_none_predicate(self):
    data = computation_building_blocks.Data('dummy', [])
    with self.assertRaises(TypeError):
      tree_analysis.extract_nodes_dependent_on_predicate(data, None)

  def test_adds_all_nodes_to_set_with_constant_true_predicate(self):
    nested_tree = computation_test_utils.create_nested_syntax_tree()
    all_nodes = tree_analysis.extract_nodes_dependent_on_predicate(
        nested_tree, lambda x: True)
    node_count = tree_analysis.count(nested_tree)
    self.assertLen(all_nodes, node_count)

  def test_adds_no_nodes_to_set_with_constant_false_predicate(self):
    nested_tree = computation_test_utils.create_nested_syntax_tree()
    all_nodes = tree_analysis.extract_nodes_dependent_on_predicate(
        nested_tree, lambda x: False)
    self.assertEmpty(all_nodes)

  def test_propogates_dependence_up_through_lambda(self):
    dummy_intrinsic = computation_building_blocks.Intrinsic(
        'dummy_intrinsic', tf.int32)
    lam = computation_building_blocks.Lambda('x', tf.int32, dummy_intrinsic)
    dependent_nodes = tree_analysis.extract_nodes_dependent_on_predicate(
        lam, dummy_intrinsic_predicate)
    self.assertIn(lam, dependent_nodes)

  def test_propogates_dependence_up_through_block_result(self):
    dummy_intrinsic = computation_building_blocks.Intrinsic(
        'dummy_intrinsic', tf.int32)
    integer_reference = computation_building_blocks.Reference('int', tf.int32)
    block = computation_building_blocks.Block([('x', integer_reference)],
                                              dummy_intrinsic)
    dependent_nodes = tree_analysis.extract_nodes_dependent_on_predicate(
        block, dummy_intrinsic_predicate)
    self.assertIn(block, dependent_nodes)

  def test_propogates_dependence_up_through_block_locals(self):
    dummy_intrinsic = computation_building_blocks.Intrinsic(
        'dummy_intrinsic', tf.int32)
    integer_reference = computation_building_blocks.Reference('int', tf.int32)
    block = computation_building_blocks.Block([('x', dummy_intrinsic)],
                                              integer_reference)
    dependent_nodes = tree_analysis.extract_nodes_dependent_on_predicate(
        block, dummy_intrinsic_predicate)
    self.assertIn(block, dependent_nodes)

  def test_propogates_dependence_up_through_tuple(self):
    dummy_intrinsic = computation_building_blocks.Intrinsic(
        'dummy_intrinsic', tf.int32)
    integer_reference = computation_building_blocks.Reference('int', tf.int32)
    tup = computation_building_blocks.Tuple(
        [integer_reference, dummy_intrinsic])
    dependent_nodes = tree_analysis.extract_nodes_dependent_on_predicate(
        tup, dummy_intrinsic_predicate)
    self.assertIn(tup, dependent_nodes)

  def test_propogates_dependence_up_through_selection(self):
    dummy_intrinsic = computation_building_blocks.Intrinsic(
        'dummy_intrinsic', [tf.int32])
    selection = computation_building_blocks.Selection(dummy_intrinsic, index=0)
    dependent_nodes = tree_analysis.extract_nodes_dependent_on_predicate(
        selection, dummy_intrinsic_predicate)
    self.assertIn(selection, dependent_nodes)

  def test_propogates_dependence_up_through_call(self):
    dummy_intrinsic = computation_building_blocks.Intrinsic(
        'dummy_intrinsic', tf.int32)
    ref_to_x = computation_building_blocks.Reference('x', tf.int32)
    identity_lambda = computation_building_blocks.Lambda(
        'x', tf.int32, ref_to_x)
    called_lambda = computation_building_blocks.Call(identity_lambda,
                                                     dummy_intrinsic)
    dependent_nodes = tree_analysis.extract_nodes_dependent_on_predicate(
        called_lambda, dummy_intrinsic_predicate)
    self.assertIn(called_lambda, dependent_nodes)

  def test_propogates_dependence_into_binding_to_reference(self):
    fed_type = computation_types.FederatedType(tf.int32, placements.CLIENTS)
    ref_to_x = computation_building_blocks.Reference('x', fed_type)
    federated_zero = computation_building_blocks.Intrinsic(
        intrinsic_defs.GENERIC_ZERO.uri, fed_type)

    def federated_zero_predicate(x):
      return isinstance(x, computation_building_blocks.Intrinsic
                       ) and x.uri == intrinsic_defs.GENERIC_ZERO.uri

    block = computation_building_blocks.Block([('x', federated_zero)], ref_to_x)
    dependent_nodes = tree_analysis.extract_nodes_dependent_on_predicate(
        block, federated_zero_predicate)
    self.assertIn(ref_to_x, dependent_nodes)


class BroadcastDependentOnAggregateTest(absltest.TestCase):

  def test_raises_on_none_comp(self):
    with self.assertRaises(TypeError):
      tree_analysis.is_broadcast_dependent_on_aggregate(None)

  def test_does_not_find_aggregate_dependent_on_broadcast(self):
    broadcast = computation_test_utils.create_dummy_called_federated_broadcast()
    value_type = broadcast.type_signature
    zero = computation_building_blocks.Data('zero', value_type.member)
    accumulate_result = computation_building_blocks.Data(
        'accumulate_result', value_type.member)
    accumulate = computation_building_blocks.Lambda(
        'accumulate_parameter', [value_type.member, value_type.member],
        accumulate_result)
    merge_result = computation_building_blocks.Data('merge_result',
                                                    value_type.member)
    merge = computation_building_blocks.Lambda(
        'merge_parameter', [value_type.member, value_type.member], merge_result)
    report_result = computation_building_blocks.Data('report_result',
                                                     value_type.member)
    report = computation_building_blocks.Lambda('report_parameter',
                                                value_type.member,
                                                report_result)
    aggregate_dependent_on_broadcast = computation_constructing_utils.create_federated_aggregate(
        broadcast, zero, accumulate, merge, report)
    result = tree_analysis.is_broadcast_dependent_on_aggregate(
        aggregate_dependent_on_broadcast)
    self.assertFalse(result[0])
    self.assertEmpty(result[1])

  def test_finds_broadcast_dependent_on_aggregate(self):
    aggregate = computation_test_utils.create_dummy_called_federated_aggregate(
        'accumulate_parameter', 'merge_parameter', 'report_parameter')
    broadcasted_aggregate = computation_constructing_utils.create_federated_broadcast(
        aggregate)
    broadcast_dependent = tree_analysis.is_broadcast_dependent_on_aggregate(
        broadcasted_aggregate)
    self.assertTrue(broadcast_dependent[0])
    self.assertNotEmpty(broadcast_dependent[1])

  def test_returns_correct_example_of_broadcast_dependent_on_aggregate(self):
    aggregate = computation_test_utils.create_dummy_called_federated_aggregate(
        'accumulate_parameter', 'merge_parameter', 'report_parameter')
    broadcasted_aggregate = computation_constructing_utils.create_federated_broadcast(
        aggregate)
    broadcast_dependent = tree_analysis.is_broadcast_dependent_on_aggregate(
        broadcasted_aggregate)
    self.assertLen(broadcast_dependent[1], 1)
    self.assertIn(broadcasted_aggregate, broadcast_dependent[1])


if __name__ == '__main__':
  absltest.main()
