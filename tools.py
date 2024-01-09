import re

import pywikibot

FULL_ARTICLE_REGEX = r'\A[\s\S]*\Z'


class FileRegexHolder:

    replaceR = None
    FLOAT_PATTERN = r'\d+(?:\.\d+)?'

    @classmethod
    def get_regex(cls, site):
        if not cls.replaceR:
            magic = ['img_baseline', 'img_border', 'img_bottom', 'img_center',
                     'img_class', 'img_framed', 'img_frameless', 'img_left',
                     'img_middle', 'img_none', 'img_right', 'img_sub',
                     'img_super', 'img_text_bottom', 'img_text_top',
                     'img_thumbnail', 'img_top']
            words = []
            for magicword in magic:
                words.extend(site.getmagicwords(magicword))
            replace = '|'.join(map(re.escape, words))
            for magicword in site.getmagicwords('img_manualthumb'):
                replace += '|' + magicword.replace('$1', cls.FLOAT_PATTERN)
            for magicword in site.getmagicwords('img_upright'):
                replace += '|' + magicword.replace('$1', cls.FLOAT_PATTERN)
            for magicword in site.getmagicwords('img_width'):
                replace += '|' + magicword.replace('$1', r'\d+')
            cls.replaceR = re.compile(replace)
        return cls.replaceR


def deduplicate(arg):
    # todo: merge with filter_unique?
    for index, member in enumerate(arg, start=1):
        while member in arg[index:]:
            arg.pop(arg.index(member, index))


def parse_image(text, site):
    # TODO: merge with .migrate_infobox.InfoboxMigratingBot.handle_image
    image = caption = None
    imgR = re.compile(r'\[\[\s*(?:%s) *:' % '|'.join(site.namespaces[6]),
                      flags=re.I)
    if imgR.match(text):
        split = text.rstrip()[:-2].split('|')
        matchR = FileRegexHolder.get_regex(site)
        while split[1:]:
            tmp = split.pop().strip()
            if not matchR.fullmatch(tmp):
                caption = tmp
                break
        if caption:
            while caption.count('[') != caption.count(']'):
                caption = f'{split.pop()}|{caption}'
            caption = caption.rstrip('.').strip()
        image = split[0].partition(':')[2].rstrip(']')
        image = pywikibot.page.url2unicode(image)
        image = re.sub('[ _]+', ' ', image).strip()

    return image, caption


def get_best_statements(statements):
    best = []
    best_rank = 'normal'
    for st in statements:
        if st.rank == best_rank:
            best.append(st)
        elif st.rank == 'preferred':
            best[:] = [st]
            best_rank = st.rank
    return best


def iter_all_snaks(data):
    for claims in data.values():
        for claim in claims:
            yield claim
            for snaks in claim.qualifiers.values():
                yield from snaks
            for ref in claim.sources:
                for snaks in ref.values():
                    yield from snaks
