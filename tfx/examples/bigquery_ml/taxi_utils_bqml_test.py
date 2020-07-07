# Lint as: python2, python3
# Copyright 2019 Google LLC. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for taxi_utils_bqml.py."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import types

import apache_beam as beam
import tensorflow as tf
import tensorflow_model_analysis as tfma
import tensorflow_transform as tft
from tensorflow_transform import beam as tft_beam
from tensorflow_transform.tf_metadata import dataset_metadata
from tensorflow_transform.tf_metadata import dataset_schema
from tensorflow_metadata.proto.v0 import schema_pb2
from tfx.components.trainer import executor as trainer_executor
from tfx.examples.bigquery_ml import taxi_utils_bqml
from tfx.utils import io_utils
from tfx.utils import path_utils


class TaxiUtilsTest(tf.test.TestCase):

  def setUp(self):
    super(TaxiUtilsTest, self).setUp()
    self._testdata_path = os.path.join(os.path.dirname(__file__), 'testdata')

  def testUtils(self):
    key = 'fare'
    xfm_key = taxi_utils_bqml._transformed_name(key)
    self.assertEqual(xfm_key, 'fare_xf')

  def testPreprocessingFn(self):
    schema_file = os.path.join(self._testdata_path, 'schema_gen/schema.pbtxt')
    schema = io_utils.parse_pbtxt_file(schema_file, schema_pb2.Schema())
    feature_spec = taxi_utils_bqml._get_raw_feature_spec(schema)
    working_dir = self.get_temp_dir()
    transform_output_path = os.path.join(working_dir, 'transform_output')
    transformed_examples_path = os.path.join(
        working_dir, 'transformed_examples')

    # Run very simplified version of executor logic.
    # TODO(kestert): Replace with tft_unit.assertAnalyzeAndTransformResults.
    # Generate legacy `DatasetMetadata` object.  Future version of Transform
    # will accept the `Schema` proto directly.
    legacy_metadata = dataset_metadata.DatasetMetadata(
        dataset_schema.from_feature_spec(feature_spec))
    decoder = tft.coders.ExampleProtoCoder(legacy_metadata.schema)
    with beam.Pipeline() as p:
      with tft_beam.Context(temp_dir=os.path.join(working_dir, 'tmp')):
        examples = (
            p
            | 'ReadTrainData' >> beam.io.ReadFromTFRecord(
                os.path.join(self._testdata_path, 'csv_example_gen/train/*'),
                coder=beam.coders.BytesCoder(),
                # TODO(b/114938612): Eventually remove this override.
                validate=False)
            | 'DecodeTrainData' >> beam.Map(decoder.decode))
        (transformed_examples, transformed_metadata), transform_fn = (
            (examples, legacy_metadata)
            | 'AnalyzeAndTransform' >> tft_beam.AnalyzeAndTransformDataset(
                taxi_utils_bqml.preprocessing_fn))

        # WriteTransformFn writes transform_fn and metadata to subdirectories
        # tensorflow_transform.SAVED_MODEL_DIR and
        # tensorflow_transform.TRANSFORMED_METADATA_DIR respectively.
        # pylint: disable=expression-not-assigned
        (transform_fn
         | 'WriteTransformFn' >> tft_beam.WriteTransformFn(
             transform_output_path))

        encoder = tft.coders.ExampleProtoCoder(transformed_metadata.schema)
        (transformed_examples
         | 'EncodeTrainData' >> beam.Map(encoder.encode)
         | 'WriteTrainData' >> beam.io.WriteToTFRecord(
             os.path.join(transformed_examples_path,
                          'train/transformed_examples.gz'),
             coder=beam.coders.BytesCoder()))
        # pylint: enable=expression-not-assigned

    # Verify the output matches golden output.
    # NOTE: we don't verify that transformed examples match golden output.
    expected_transformed_schema = io_utils.parse_pbtxt_file(
        os.path.join(
            self._testdata_path,
            'transform/transform_output/transformed_metadata/schema.pbtxt'),
        schema_pb2.Schema())
    transformed_schema = io_utils.parse_pbtxt_file(
        os.path.join(transform_output_path,
                     'transformed_metadata/schema.pbtxt'),
        schema_pb2.Schema())
    # Clear annotations so we only have to test main schema.
    for feature in transformed_schema.feature:
      feature.ClearField('annotation')
    transformed_schema.ClearField('annotation')
    self.assertEqual(transformed_schema, expected_transformed_schema)

  def testTrainerFn(self):
    temp_dir = os.path.join(
        os.environ.get('TEST_UNDECLARED_OUTPUTS_DIR', self.get_temp_dir()),
        self._testMethodName)

    schema_file = os.path.join(self._testdata_path, 'schema_gen/schema.pbtxt')
    output_dir = os.path.join(temp_dir, 'output_dir')
    trainer_fn_args = trainer_executor.TrainerFnArgs(
        train_files=os.path.join(self._testdata_path,
                                 'transform/transformed_examples/train/*.gz'),
        transform_output=os.path.join(self._testdata_path,
                                      'transform/transform_output/'),
        output_dir=output_dir,
        serving_model_dir=os.path.join(temp_dir, 'serving_model_dir'),
        eval_files=os.path.join(self._testdata_path,
                                'transform/transformed_examples/eval/*.gz'),
        schema_file=schema_file,
        train_steps=1,
        eval_steps=1,
        verbosity='INFO',
        base_model=os.path.join(self._testdata_path,
                                'trainer/current/serving_model_dir'))
    schema = io_utils.parse_pbtxt_file(schema_file, schema_pb2.Schema())
    training_spec = taxi_utils_bqml.trainer_fn(trainer_fn_args, schema)

    estimator = training_spec['estimator']
    train_spec = training_spec['train_spec']
    eval_spec = training_spec['eval_spec']
    eval_input_receiver_fn = training_spec['eval_input_receiver_fn']

    self.assertIsInstance(estimator, tf.estimator.Estimator)
    self.assertIsInstance(train_spec, tf.estimator.TrainSpec)
    self.assertIsInstance(eval_spec, tf.estimator.EvalSpec)
    self.assertIsInstance(eval_input_receiver_fn, types.FunctionType)

    # Train for one step, then eval for one step.
    eval_result, exports = tf.estimator.train_and_evaluate(
        estimator, train_spec, eval_spec)
    self.assertGreater(eval_result['loss'], 0.0)
    self.assertEqual(len(exports), 1)
    self.assertGreaterEqual(len(tf.io.gfile.listdir(exports[0])), 1)

    # Export the eval saved model.
    eval_model_dir = os.path.join(output_dir,
                                  path_utils.EVAL_MODEL_DIR)
    eval_savedmodel_path = tfma.export.export_eval_savedmodel(
        estimator=estimator,
        export_dir_base=eval_model_dir,
        eval_input_receiver_fn=eval_input_receiver_fn)
    self.assertGreaterEqual(len(tf.io.gfile.listdir(eval_savedmodel_path)), 1)

    # Test exported serving graph.
    with tf.compat.v1.Session() as sess:
      metagraph_def = tf.compat.v1.saved_model.loader.load(
          sess, [tf.saved_model.SERVING], exports[0])
      self.assertIsInstance(metagraph_def, tf.compat.v1.MetaGraphDef)


if __name__ == '__main__':
  tf.test.main()
