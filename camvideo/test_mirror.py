import unittest
from mirror import Gesture, TouchMirror


class MirrorTests(unittest.TestCase):
    def gesture(self):
        g=Gesture((0,1000,0,2000))
        g.feed('ABS_MT_TRACKING_ID','00000001')
        g.feed('ABS_MT_POSITION_X','000001f4')
        g.feed('ABS_MT_POSITION_Y','000003e8')
        g.feed('SYN_REPORT','00000000')
        return g

    def test_tap_waits_for_release_and_normalizes(self):
        g=self.gesture()
        self.assertIsNone(g.feed('SYN_REPORT','00000000'))
        g.feed('ABS_MT_TRACKING_ID','ffffffff')
        result=g.feed('SYN_REPORT','00000000')
        self.assertEqual(result[:4],(.5,.5,.5,.5))
        self.assertIsNone(g.feed('SYN_REPORT','00000000'))

    def test_swipe_keeps_start_and_end(self):
        g=self.gesture()
        g.feed('ABS_MT_POSITION_X','000003e8')
        g.feed('ABS_MT_TRACKING_ID','ffffffff')
        self.assertEqual(g.feed('SYN_REPORT','00000000')[:4],(.5,.5,1,.5))

    def test_multitouch_is_not_replayed_as_single_touch(self):
        g=self.gesture()
        g.feed('ABS_MT_SLOT','00000001')
        g.feed('ABS_MT_TRACKING_ID','00000002')
        g.feed('ABS_MT_SLOT','00000000')
        g.feed('ABS_MT_TRACKING_ID','ffffffff')
        self.assertIsNone(g.feed('SYN_REPORT','00000000'))

    def test_coordinates_scale_to_target(self):
        m=TouchMirror('adb',lambda:{})
        calls=[];m.run_adb=lambda *args:calls.append(args)
        m.send('follower',(.5,.5,.5,.5,50),(101,201))
        self.assertEqual(calls,[('follower','shell','input','tap','50','100')])

if __name__=='__main__':unittest.main()
