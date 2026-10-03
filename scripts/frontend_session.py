"""Toolkit-free UI session: one service and one reviewed operation at a time."""
from __future__ import annotations
from pathlib import Path
import threading
import library_media
from desktop_service import DesktopService


class FrontendSession:
    def __init__(self, demo=False):
        self.demo=demo;self.service=DesktopService()
        self.settings=dict(library_media.DEFAULTS) if demo else library_media.load_settings(self.service.config)
        self.games=[];self.selected=set();self.review=None;self.revision=0
        self.lock=threading.RLock();self.cancel_event=threading.Event()

    def invalidate(self):
        self.revision+=1;self.review=None

    def select(self,key,active):
        with self.lock:
            if key not in {g['game'] for g in self.games}:raise ValueError('Game is no longer in the library.')
            self.selected.add(key) if active else self.selected.discard(key)
            self.invalidate()

    def preferences(self,**values):
        with self.lock:
            if set(values)-set(library_media.DEFAULTS):raise ValueError('Unknown preference.')
            candidate={**self.settings,**values}
            if not self.demo:library_media.save_settings(self.service.config,candidate)
            self.settings=candidate;self.invalidate()

    def scan(self):
        with self.lock:
            self.games=self.service.scan_all(self.settings.get('extra_folders',[]))
            self.selected.intersection_update(g['game'] for g in self.games);self.invalidate()
            return self.games

    def prepare(self,operation='install',targets=None,visual_settings=None):
        with self.lock:
            keys=self.selected if targets is None else set(targets)
            if not keys <= {g['game'] for g in self.games}:raise ValueError('Game selection changed; refresh the library.')
            rows=[g for g in self.games if g['game'] in keys]
            if not rows:raise ValueError('Select games first.')
            if self.demo:
                self.review={'kind':'demo','rows':[{'name':g['name'],'detail':'Write-disabled preview'} for g in rows],'blocked':[]}
            else:
                settings=dict(self.settings)
                if visual_settings:
                    allowed={'nr_strength','mfg_multiplier','sharpening_strength'}
                    if set(visual_settings)-allowed:raise ValueError('Unsupported per-game setting.')
                    settings.update(visual_settings)
                self.review=self.service.prepare(rows,self.settings.get('default_profile','mfg-only'),operation,visual_settings=settings)
            self.cancel_event.clear()
            return {'revision':self.revision,'rows':self.review['rows'],'blocked':self.review.get('blocked',[]),'demo':self.demo}

    def apply(self,revision):
        with self.lock:
            if self.demo:raise ValueError('Demo mode never modifies games.')
            if self.review is None or revision!=self.revision:raise ValueError('Selection or settings changed. Review again.')
            review=self.review;self.review=None
            if not review.get('plans'):raise ValueError('No compatible changes to apply.')
            review['cancel_event']=self.cancel_event
            return self.service.execute(review)

    def cancel(self):
        self.cancel_event.set()


def library_columns(width,preferred=7,view='posters'):
    """Same density thresholds as the canonical Classic Library."""
    usable=max(1,int(width)-32);n=max(3,min(9,int(preferred)));gap=16
    minimum=200 if view=='posters' else 220
    maximum=420 if view=='posters' else 520
    while n>3 and (usable-gap*(n-1))/n<minimum:n-=1
    while n<9 and (usable-gap*(n-1))/n>maximum:n+=1
    return n
