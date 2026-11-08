"""Date default and interactive Tk spinbox regression tests."""
from __future__ import annotations
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gui import default_end_date, Plotter


class PeriodDefaultsTests(unittest.TestCase):
    def test_inclusive_windows(self):
        self.assertEqual(default_end_date('2017-06-12','Daily'),'2017-06-12')
        self.assertEqual(default_end_date('2017-06-12','Weekly'),'2017-06-18')
        self.assertEqual(default_end_date('2017-06-12','Monthly'),'2017-07-11')
        self.assertEqual(default_end_date('2017-06-12','Yearly'),'2018-06-11')
        self.assertEqual(default_end_date('2020-02-01','Monthly'),'2020-02-29')
        self.assertEqual(default_end_date('2019-01-01','Yearly'),'2019-12-31')
    def test_bad_period(self):
        with self.assertRaises(ValueError):
            default_end_date('2020-01-01','Bad')


class TkDateTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        try:
            self.app=Plotter()
        except tk.TclError as ex:
            self.skipTest(f'Tk display unavailable: {ex}')
        self.app.withdraw()
    def tearDown(self):
        if hasattr(self,'app'):
            self.app.destroy()

    def test_period_change_sets_end_automatically(self):
        a=self.app
        a.start_date.set('2017-06-12')
        for period,expected in [('Daily','2017-06-12'),('Weekly','2017-06-18'),
                                ('Monthly','2017-07-11'),('Yearly','2018-06-11')]:
            a.period.set(period)
            a.on_period_changed()
            self.assertEqual(a.end_date.get(),expected)
            self.assertFalse(a._range_is_custom)

    def test_detail_dropdown_has_weekly_monthly_and_period_change_resets_default(self):
        a=self.app
        detail_boxes=[]
        from tkinter import ttk
        def visit(widget):
            for child in widget.winfo_children():
                if isinstance(child,ttk.Combobox) and child.cget('textvariable') == str(a.detail):
                    detail_boxes.append(child)
                visit(child)
        visit(a)
        self.assertEqual(len(detail_boxes),1)
        self.assertEqual(list(detail_boxes[0]['values']),
                         ['Default','Hourly','Daily','Weekly','Monthly'])
        a.detail.set('Hourly')
        a.period.set('Monthly')
        a.on_period_changed()
        self.assertEqual(a.detail.get(),'Default')
        a.period.set('Yearly')
        a.detail.set('Weekly')
        a.draw(silent=True)

    def test_spinbox_and_custom_override(self):
        a=self.app
        a.start_date.set('2020-02-01')
        a.period.set('Monthly');a.on_period_changed()
        self.assertEqual(a.end_date.get(),'2020-02-29')
        a.start_entry.d.set('02');a.start_entry._commit()
        self.assertEqual(a.start_date.get(),'2020-02-02')
        self.assertEqual(a.end_date.get(),'2020-03-01')
        a.end_entry.m.set('04');a.end_entry._commit()
        self.assertEqual(a.end_date.get(),'2020-04-01')
        self.assertTrue(a._range_is_custom)
        a.start_entry.d.set('03');a.start_entry._commit()
        self.assertEqual(a.start_date.get(),'2020-02-03')
        self.assertEqual(a.end_date.get(),'2020-04-01')
        a.period.set('Weekly');a.on_period_changed()
        self.assertEqual(a.end_date.get(),'2020-02-09')
        self.assertFalse(a._range_is_custom)

    def test_previous_next_moves_default_window(self):
        a=self.app
        a.start_date.set('2017-06-12')
        a.period.set('Weekly');a.on_period_changed()
        a.move_date(1)
        self.assertEqual(a.start_date.get(),'2017-06-19')
        self.assertEqual(a.end_date.get(),'2017-06-25')
        a.move_date(-1)
        self.assertEqual(a.start_date.get(),'2017-06-12')
        self.assertEqual(a.end_date.get(),'2017-06-18')

    def test_plot_redraw_after_changes(self):
        import pandas as pd
        a=self.app
        idx=pd.date_range('2017-06-12',periods=24*40,freq='h')
        a.load_current=pd.DataFrame({'residential':2.,'commercial':3.,
                                     'manufacturing':5.,'total':10.},index=idx)
        a.start_date.set('2017-06-12');a.period.set('Daily');a.on_period_changed()
        a.draw()
        self.assertEqual(len(a.plot_tables['load_hourly']),24)
        a.period.set('Weekly');a.on_period_changed()
        a.draw()
        self.assertEqual(len(a.plot_tables['load_daily']),7)
        a.bus_checks['commercial'].set(False)
        a.request_redraw()
        a.update()
        # The plot updates on the event loop after a short debounce.
        a.after(120,a.quit)
        a.mainloop()
        self.assertEqual(set(a.plot_tables['load_daily'].columns),
                         {'residential','manufacturing','total'})


if __name__=='__main__':
    unittest.main()
