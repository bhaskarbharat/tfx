# Lint as: python2, python3
# Copyright 2019 Google LLC. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Deprecated location for the TFX ImporterNode.

The new location is `tfx.dsl.components.common.importer_node.ImporterNode`.
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from tfx.dsl.components.common import importer_node
from tfx.utils import deprecation_utils


# Constant to access importer importing result from importer output dict.
IMPORT_RESULT_KEY = importer_node.IMPORT_RESULT_KEY
# Constant to access artifact uri from importer exec_properties dict.
SOURCE_URI_KEY = importer_node.SOURCE_URI_KEY
# Constant to access artifact properties from importer exec_properties dict.
PROPERTIES_KEY = importer_node.PROPERTIES_KEY
# Constant to access artifact properties from importer exec_properties dict.
CUSTOM_PROPERTIES_KEY = importer_node.CUSTOM_PROPERTIES_KEY
# Constant to access re-import option from importer exec_properties dict.
REIMPORT_OPTION_KEY = importer_node.REIMPORT_OPTION_KEY

ImporterNode = deprecation_utils.deprecated_alias(  # pylint: disable=invalid-name
    deprecated_name='tfx.components.common_nodes.importer_node.ImporterNode',
    name='tfx.dsl.components.common.importer_node.ImporterNode',
    func_or_class=importer_node.ImporterNode)
