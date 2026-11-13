import io, sys
wxml_path = r'E:\MyPrj\zhpt-new\frontend\packageVocational\pages\vocational-club-courses\vocational-club-courses.wxml'
s = open(wxml_path, encoding='utf-8').read()
buf = io.StringIO()
sys.stdout = buf
print('unicode char in wxml:', '\ue65f' in s)
print('van-icon removed:', '<van-icon name="arrow-up' not in s)
print('text vi count:', s.count('<text class="vi"'))
sys.stdout = sys.__stdout__
print(buf.getvalue().replace('\ue65f', 'U+E65F'))
