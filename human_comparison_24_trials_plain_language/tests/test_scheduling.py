import random
import sys
import unittest
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scheduling import build_schedule, validate_pairs


def pairs(count=4, animals=('seal','whale','dolphin')):
    return [dict(pair_id=f'{animal}_{i}_{baseline}', source_id=f'{animal}_{i}',animal=animal,baseline=baseline)
            for animal in animals for baseline in ('black_mask','blurring') for i in range(count)]


class SchedulingTests(unittest.TestCase):
    def test_exact_counts_across_many_sessions(self):
        pool=pairs(10)
        lookup={p['pair_id']:p for p in pool}
        for seed in range(100):
            schedule=build_schedule(pool,random.Random(seed))
            self.assertEqual(len(schedule),24)
            self.assertEqual(len({t['pair_id'] for t in schedule}),24)
            counts=Counter((lookup[t['pair_id']]['animal'],lookup[t['pair_id']]['baseline']) for t in schedule)
            self.assertEqual(len(counts),6)
            self.assertTrue(all(n==4 for n in counts.values()))
            for item in schedule:
                baseline=lookup[item['pair_id']]['baseline']
                self.assertEqual({item['left_method'],item['right_method']},{'remove',baseline})

    def test_seed_reproduces_schedule_and_other_seeds_vary(self):
        pool=pairs(10)
        a=build_schedule(pool,random.Random(1))
        self.assertEqual(a,build_schedule(pool,random.Random(1)))
        self.assertNotEqual(a,build_schedule(pool,random.Random(2)))
        left_methods={item['left_method'] for seed in range(10) for item in build_schedule(pool,random.Random(seed))}
        self.assertEqual(left_methods,{'remove','blurring','black_mask'})

    def test_four_sources_per_species_are_sufficient(self):
        pool=pairs(4)
        schedule=build_schedule(pool,random.Random(1))
        self.assertEqual({t['pair_id'] for t in schedule},{p['pair_id'] for p in pool})

    def test_fewer_than_four_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'at least 4'):
            validate_pairs(pairs(3))

    def test_species_count_is_enforced(self):
        for animals in [('seal','whale'),('seal','whale','dolphin','turtle')]:
            with self.assertRaisesRegex(ValueError,'exactly 3'):
                validate_pairs(pairs(4,animals))

    def test_missing_baseline_and_duplicate_pair_are_rejected(self):
        pool=[p for p in pairs() if not(p['animal']=='seal' and p['baseline']=='blurring')]
        with self.assertRaisesRegex(ValueError,'seal/blurring'):
            validate_pairs(pool)
        pool=pairs()
        with self.assertRaisesRegex(ValueError,'Duplicate comparison'):
            validate_pairs(pool+[pool[0]])

    def test_duplicate_source_in_a_cell_is_rejected(self):
        pool=pairs(5)
        pool[1]['source_id']=pool[0]['source_id']
        with self.assertRaisesRegex(ValueError,'Duplicate source'):
            validate_pairs(pool)


if __name__=='__main__':
    unittest.main()
