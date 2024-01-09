#!/usr/bin/python
from itertools import chain
from operator import methodcaller

import pywikibot

from pywikibot import pagegenerators
from pywikibot.bot import SingleSiteBot, ExistingPageBot

from custome_fixes import all_fixes


class WikitextFixingBot(SingleSiteBot, ExistingPageBot):

    use_redirects = False

    '''
    Class for bots that save wikitext. It uses all demanded fixes from
    custome_fixes.py and applies them before cosmetic changes are
    executed.

    You can enable each fix by using its name as a command line argument
    or all fixes using -all (then, each used fix is excluded).
    '''

    def __init__(self, **kwargs):
        do_all = kwargs.pop('all', False) is True
        self.fixes = []
        for fix, cls in all_fixes.items():
            if do_all:
                demand = fix not in kwargs
                kwargs.pop(fix, None)
            else:
                demand = bool(kwargs.pop(fix, False))
            if demand:
                options = {opt: kwargs.pop(opt) for opt in cls.options.keys() if opt in kwargs}
                self.fixes.append(cls(**options))

        self.fixes.sort(key=lambda fix: fix.order)

        super().__init__(**kwargs)
        for fix in self.fixes:
            fix.site = self.site
        if not self.generator:
            pywikibot.info('No generator provided, making own generator...')
            self.generator = pagegenerators.PreloadingGenerator(
                chain.from_iterable(map(methodcaller('generator'), self.fixes)))

    def treat_page(self):
        summaries = []
        page = self.current_page
        old_text = page.text
        callbacks = self.applyFixes(page, summaries)
        if not summaries:
            pywikibot.info('No replacements worth saving')
            return
        pywikibot.showDiff(old_text, page.text)
        # todo: method
        callback = lambda _, exc: [cb() for cb in callbacks if not exc]
        # todo: put_current
        self._save_page(page, page.save, callback=callback,
                        summary='; '.join(summaries))

    def applyFixes(self, page, summaries=[]):
        callbacks = []
        for fix in self.fixes:
            fix.apply(page, summaries, callbacks)
        return callbacks

    def userPut(self, page, oldtext, newtext, **kwargs):
        if oldtext.rstrip() == newtext.rstrip():
            pywikibot.info(
                f'No changes were needed on {page.title(as_link=True)}')
            return

        self.current_page = page

        if show_diff := kwargs.pop('show_diff', not self.opt['always']):
            pywikibot.showDiff(oldtext, newtext)

        if 'summary' in kwargs:
            pywikibot.info(f"Edit summary: {kwargs['summary']}")

        page.text = newtext
        return self._save_page(page, self.fix_wikitext, page, **kwargs)

    def fix_wikitext(self, page, *args, **kwargs):
        summaries = [kwargs['summary']]
        callbacks = self.applyFixes(page, summaries)

        kwargs['summary'] = '; '.join(summaries)
        # todo: method
        kwargs['callback'] = lambda _, exc: [cb() for cb in callbacks
                                             if not exc]
        page.save(*args, **kwargs)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
    for arg in genFactory.handle_args(local_args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator(preload=True)
    bot = WikitextFixingBot(generator=generator, **options)
    bot.run()


if __name__ == '__main__':
    main()
