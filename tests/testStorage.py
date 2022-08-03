import json
import logging
import os
import time
from datetime import datetime
from unittest import TestCase, main

import pymongo
from mcrit.config.StorageConfig import StorageConfig
from mcrit.minhash.MinHash import MinHash
from mcrit.storage.FunctionEntry import FunctionEntry
from mcrit.storage.SampleEntry import SampleEntry
from mcrit.storage.StorageFactory import StorageFactory
from smda.common.SmdaReport import SmdaReport

from .context import config

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)


class MemoryStorageTest(TestCase):
    def setUp(self):
        self._config = StorageConfig(
            STORAGE_METHOD=StorageFactory.STORAGE_METHOD_MEMORY,
            STORAGE_DROP_DISASSEMBLY=False,
        )
        self.storage = StorageFactory.getStorage(self._config)
        # get example_file_path
        THIS_FILE_PATH = str(os.path.abspath(__file__))
        PROJECT_ROOT = str(os.path.abspath(os.sep.join([THIS_FILE_PATH, "..", ".."])))
        self.example_file_path = os.sep.join([PROJECT_ROOT, "tests", "example_report.smda"])

    def tearDown(self):
        self.storage.clearStorage()

    def testBasicStorageUsage(self):
        self.storage.clearStorage()
        smda_report = SmdaReport.fromFile(self.example_file_path)
        self.storage.addSmdaReport(smda_report)
        stats = self.storage.getStats()
        self.assertEqual(1, stats["num_samples"])
        self.assertEqual(10, stats["num_functions"])
        self.assertEqual(10, stats["num_pichashes"])

    def testFamilyHandling(self):
        self.storage.clearStorage()
        self.storage.addFamily("family_1")
        self.storage.addFamily("family_2")
        id_3 = self.storage.addFamily("family_3")
        id_3_again = self.storage.addFamily("family_3")
        self.assertEqual(id_3, 3)
        self.assertEqual(id_3_again, 3)

        # family 0 is default: ""
        self.assertEqual(0, self.storage.getFamilyId(""))
        self.assertEqual("", self.storage.getFamily(0).family_name)
        self.assertEqual(4, len(self.storage.getFamilyIds()))
        self.assertEqual("family_1", self.storage.getFamily(1).family_name)
        self.assertEqual(3, self.storage.getFamilyId("family_3"))
        self.assertIsNone(self.storage.getFamily(1000))
        self.assertIsNone(self.storage.getFamilyId("nonexistent"))

    def testSampleHandling(self):
        self.storage.clearStorage()
        # TODO: different samples required, because addSmdaReport wont accept identical hashes
        with open(self.example_file_path, "r") as fjson:
            smda_json = json.load(fjson)
        smda_report_a = SmdaReport.fromDict(smda_json)
        smda_report_a.family = "family_1"
        smda_report_a.is_library = False
        smda_report_a.sha256 = 64 * "a"
        smda_report_b = SmdaReport.fromDict(smda_json)
        smda_report_b.family = "family_1"
        smda_report_b.is_library = False
        smda_report_b.sha256 = 64 * "b"
        smda_report_c = SmdaReport.fromDict(smda_json)
        smda_report_c.family = "family_2"
        smda_report_c.is_library = False
        smda_report_c.sha256 = 64 * "c"
        smda_report_d = SmdaReport.fromDict(smda_json)
        smda_report_d.family = "family_3"
        smda_report_d.is_library = True
        smda_report_d.version = "3.42"
        smda_report_d.sha256 = 64 * "d"
        self.storage.addSmdaReport(smda_report_a)
        self.storage.addSmdaReport(smda_report_b)
        self.storage.addSmdaReport(smda_report_c)
        sample_entry_d = self.storage.addSmdaReport(smda_report_d)
        self.assertIsInstance(sample_entry_d, SampleEntry)
        self.assertEqual(sample_entry_d.sample_id, 3)
        self.assertEqual(None, self.storage.addSmdaReport(smda_report_d))

        self.assertEqual([0, 1, 2, 3], self.storage.getSampleIds())
        self.assertTrue(self.storage.isSampleId(0))
        self.assertFalse(self.storage.isSampleId(4))
        self.assertEqual(None, self.storage.getSampleById(4))
        self.assertEqual(2, self.storage.getSampleById(2).sample_id)
        self.assertEqual(None, self.storage.getSampleIdByFunctionId(40))
        self.assertEqual(3, self.storage.getSampleIdByFunctionId(30))
        self.assertEqual(None, self.storage.getSamplesByFamilyId(4))
        self.assertEqual([0, 1], [s.sample_id for s in self.storage.getSamplesByFamilyId(1)])
        self.assertEqual(None, self.storage.getLibraryInfoForSampleId(2))
        self.assertEqual({"family": "family_3", "version": "3.42"}, self.storage.getLibraryInfoForSampleId(3))

        self.assertEqual(None, self.storage.getLibraryInfoForSampleId(1000))

        self.assertEqual(0, self.storage.getSampleBySha256(64* "a").sample_id)
        self.assertEqual(None, self.storage.getSampleBySha256(64* "z"))

        self.assertFalse(self.storage.deleteSample(1000))

        delete_result = self.storage.deleteSample(3)
        self.assertTrue(delete_result)
        self.assertEqual(None, self.storage.getSampleById(3))
        # functions, minhashes will be cascadically deleted
        self.assertEqual(None, self.storage.getSampleIdByFunctionId(30))
        new_report_d = self.storage.addSmdaReport(smda_report_d)
        self.assertIsNotNone(new_report_d)
        self.assertEqual(new_report_d.sample_id, 4)
        self.assertTrue(self.storage.isFunctionId(49))



    def testFunctionHandling(self):
        self.storage.clearStorage()
        # TODO use SmdaReport.fromFile
        with open(self.example_file_path, "r") as fjson:
            smda_json = json.load(fjson)
        smda_report_a = SmdaReport.fromDict(smda_json)
        smda_report_a.sha256 = 64 * "a"
        smda_report_a.family = "family_1"
        smda_report_b = SmdaReport.fromDict(smda_json)
        smda_report_b.family = "family_1"
        smda_report_b.sha256 = 64 * "b"
        self.storage.addSmdaReport(smda_report_a)
        self.storage.addSmdaReport(smda_report_b)

        self.assertTrue(self.storage.isFunctionId(0))
        self.assertTrue(self.storage.isFunctionId(1))
        self.assertFalse(self.storage.isFunctionId(30))
        functions = self.storage.getFunctionsBySampleId(1)
        self.assertIsNotNone(functions)
        self.assertEqual(list(range(10,20)), [entry.function_id for entry in functions])

        function = self.storage.getFunctionById(1)
        self.assertEqual(1, function.function_id)
        self.assertNotEqual({}, function.xcfg)
        self.storage.deleteXcfgForSampleId(function.sample_id)
        function = self.storage.getFunctionById(1)
        self.assertEqual({}, function.xcfg)
        function2 = self.storage.getFunctionById(15)
        self.assertNotEqual({}, function2.xcfg)
        self.storage.deleteXcfgData()
        function2 = self.storage.getFunctionById(15)
        self.assertEqual({}, function2.xcfg)

        self.assertIsNone(self.storage.getFunctionById(1000))
        functions = self.storage.getFunctionsBySampleId(1000)
        self.assertIsNone(functions)

        self.storage.deleteXcfgForSampleId(1000)

    def testHashHandling(self):
        storage_config = StorageConfig()
        storage_config.STORAGE_BANDS = {2: 2, 3: 8}
        storage_config.STORAGE_BAND_SEED = 0

        self.storage.clearStorage()
        with open(self.example_file_path, "r") as fjson:
            smda_json = json.load(fjson)
        smda_report_a = SmdaReport.fromDict(smda_json)
        smda_report_a.sha256 = 64 * "a"
        smda_report_a.family = "family_1"
        smda_report_b = SmdaReport.fromDict(smda_json)
        smda_report_b.family = "family_1"
        smda_report_b.sha256 = 64 * "b"
        self.storage.addSmdaReport(smda_report_a)
        self.storage.addSmdaReport(smda_report_b)

        # pichash tests
        sample_entry = SampleEntry(smda_report_a, sample_id=1, family_id=1)
        function_entry = FunctionEntry(sample_entry, smda_report_a.getFunction(356), 1)
        # Will this work?
        initial_pichash = function_entry.pichash
        pichashes = self.storage.getPicHashMatchesByFunctionId(1)
        self.assertTrue(initial_pichash in pichashes)
        sample_and_function_ids = self.storage.getMatchesForPicHash(initial_pichash)
        self.assertTrue(self.storage.isPicHash(initial_pichash))
        self.assertEqual(set([(0,1), (1, 11)]), sample_and_function_ids)

        not_a_pichash = 0
        self.assertEqual(set(), self.storage.getMatchesForPicHash(not_a_pichash))

        pichashes_by_function_ids = self.storage.getPicHashMatchesByFunctionIds(list(range(10,20)))
        pichashes_by_sample_id = self.storage.getPicHashMatchesBySampleId(1)
        self.assertEqual(pichashes_by_function_ids, pichashes_by_sample_id)

        self.assertIsNone(self.storage.getPicHashMatchesBySampleId(1000))
        self.assertIsNone(self.storage.getPicHashMatchesByFunctionId(1000))
        self.assertEqual(pichashes, self.storage.getPicHashMatchesByFunctionIds([1, 1, 1000]))

        # minhash tests
        # TODO check if MinHash initialization works
        minhash_a = MinHash(
            function_id=1, minhash_signature=[0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39]
        )
        minhash_b = MinHash(
            function_id=3, minhash_signature=[0x30, 0x31, 0x30, 0x33, 0x30, 0x30, 0x30, 0x37, 0x38, 0x39]
        )
        function_entry = self.storage.getFunctionById(1)
        self.assertEqual(b"", function_entry.minhash)
        status = self.storage.addMinHash(minhash_a)
        self.assertTrue(status)
        self.storage.addMinHash(minhash_b)
        function_entry = self.storage.getFunctionById(1)
        minhash_queried = self.storage.getMinHashByFunctionId(1)
        self.assertEqual(minhash_a.getMinHash(), minhash_queried)
        minhash_queried = self.storage.getMinHashByFunctionId(3)
        self.assertEqual(minhash_b.getMinHash(), minhash_queried)

        self.assertFalse(self.storage.addMinHash(MinHash(function_id=1000)))
        self.assertFalse(self.storage.addMinHash(MinHash(function_id=None)))

        self.assertEqual(None, self.storage.getMinHashByFunctionId(1000))

        # minhash band tests
        candidates = self.storage.getCandidatesForMinHash(minhash_a)
        self.assertEqual(set([1, 3]), candidates)

        candidates = self.storage.getCandidatesForMinHashes({1000: minhash_a})
        self.assertEqual({1000: set([1, 3])}, candidates)

    def testMatchingCache(self):
        cache = self.storage.createMatchingCache([])
        self.assertTrue(hasattr(cache, "getMinHashByFunctionId"))
        self.assertTrue(hasattr(cache, "getSampleIdByFunctionId"))


### Added mongo attribute
from nose.plugins.attrib import attr


@attr("mongo")
class MongoDbStorageTest(MemoryStorageTest):
    def setUp(self):
        self._config = StorageConfig(
            STORAGE_METHOD=StorageFactory.STORAGE_METHOD_MONGODB,
            STORAGE_SERVER=os.environ.get("TEST_MONGODB"),
            STORAGE_MONGODB_DBNAME="test_mongodbstorage_mcrit",
            STORAGE_DROP_DISASSEMBLY=False,
        )
        self.storage = StorageFactory.getStorage(self._config)
        # get example_file_path
        THIS_FILE_PATH = str(os.path.abspath(__file__))
        PROJECT_ROOT = str(os.path.abspath(os.sep.join([THIS_FILE_PATH, "..", ".."])))
        self.example_file_path = os.sep.join([PROJECT_ROOT, "tests", "example_report.smda"])


if __name__ == "__main__":
    main()
