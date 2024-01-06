#!/usr/bin/python
import re

from datetime import datetime
from itertools import chain

import pywikibot

from pywikibot import i18n, textlib
from pywikibot.bot import ExistingPageBot, SingleSiteBot
from pywikibot.pagegenerators import PreloadingGenerator

birth = {
    'wikipedia': {
        'cs': r'Narození v roce (\d+)',
    },
}

death = {
    'wikipedia': {
        'cs': 'Úmrtí v roce %d',
    },
}

replace_pattern = '[[{inside}]] ({left}{year1}{right}–{left}{year2}{right})'


class DeathDateUpdatingBot(SingleSiteBot, ExistingPageBot):

    use_redirects = False

    def __init__(self, **kwargs):
        self.available_options.update({'year': datetime.now().year})
        super().__init__(**kwargs)
        self.categoryR = re.compile(i18n.translate(self.site, birth))
        self.year = self.opt['year']

    @property
    def generator(self):
        while True:
            category = pywikibot.Category(
                self.site, i18n.translate(self.site, death) % self.year)
            yield from category.articles(content=True, namespaces=[0])
            self.year -= 1

    def treat_page(self):
        page = self.current_page
        categories = textlib.getCategoryLinks(page.text, site=self.site)
        titles = (cat.title(with_ns=False, with_section=False,
                            allow_interwiki=False, insite=self.site)
                  for cat in categories)
        matches = [match for match in map(self.categoryR.fullmatch, titles)
                   if match]
        if not matches:
            pywikibot.info('No birthdate category found')
            return
        fullmatch = matches.pop()
        if matches:
            pywikibot.info('Multiple birthdate categories found')
            return
        birth_date = fullmatch[1]
        search_query = f'linksto:"{page.title()}"'  # todo: sanitize?
        search_query += r' insource:/\[\[[^\[\]]+\]\]'
        search_query += fr' +\(\* *\[*{birth_date}\]*\)/'
        search_query += ' -intitle:"Seznam"'
        pattern = r'\[\[((?:%s)(?:\|[^\[\]]+)?)\]\]' % '|'.join(
            re.escape(p.title()) for p in chain([page], page.backlinks(
                follow_redirects=False, filter_redirects=True, namespaces=[0])))
        pattern += fr' +\(\* *(\[\[)?({birth_date})(\]\])?\)'
        regex = re.compile(pattern)
        for ref_page in PreloadingGenerator(
                page.site.search(search_query, namespaces=[0])):
            new_text, num = regex.subn(self.replace_callback, ref_page.text)
            if num:
                self.userPut(ref_page, ref_page.text, new_text,
                             summary='doplnění data úmrtí')

    def replace_callback(self, match):
        inside, left, year1, right = match.groups('')
        return replace_pattern.format(
            inside=inside, left=left, right=right, year1=year1,
            year2=self.year)


def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    bot = DeathDateUpdatingBot(**options)
    bot.run()


if __name__ == '__main__':
    main()
