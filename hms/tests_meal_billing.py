"""
Meal billing & payment tests for Touch and Solve (TNS) HMS.

Covers the 12 required scenarios plus a regression test for the ৳2500 outstanding
bug (outstanding must equal the sum of valid unpaid today+past meal bills, excluding
future dates, with no stale/duplicated/shared-payment rows counted twice).

Billing rule under test:
    charge(booking, date, meal_type) = configured price
      iff a saved MealPreference exists with status='on' AND is_locked=True
      (is_locked == the meal's cutoff has passed).
    A missing preference is treated as OFF (never charged).
    Future dates are never billed, never payable, never in outstanding.
"""
from datetime import datetime, date
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.utils import timezone

from hms.models import (
    Hostel, RoomType, Room, Bed, Booking, MealSettings, MealPreference, MealBill, Payment,
)

User = get_user_model()
TZ = ZoneInfo('Asia/Dhaka')
MEAL_TIMES = {'breakfast': 7, 'lunch': 12, 'dinner': 19}


def _aware(y=2026, mo=8, d=31, h=18, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


class MealBillingTestBase(TestCase):
    """Build a minimal isolated Touch and Solve (TNS) fixture."""

    def setUp(self):
        self.renter = User.objects.create_user(
            email='renter_meal_test@example.com', password='pass12345',
            full_name='Meal Renter', role='RENTER',
        )
        self.manager = User.objects.create_user(
            email='mgr_meal_test@example.com', password='pass12345',
            full_name='Meal Mgr', role='HOSTEL_MANAGER',
        )
        self.admin = User.objects.create_superuser(
            email='admin_meal_test@example.com', password='pass12345', full_name='Meal Admin',
        )
        self.hostel = Hostel.objects.create(
            name='Touch and Solve (TNS) Hostel', slug='nestora-hostel-test', city='Dhaka',
            address='Test Road', manager=self.manager, is_active=True,
        )
        self.room_type = RoomType.objects.create(name='Standard', description='test')
        self.room = Room.objects.create(
            hostel=self.hostel, room_type=self.room_type, room_number='101',
            capacity=4, rent=2800, status='available', is_active=True,
        )
        self.bed = Bed.objects.create(room=self.room, bed_number='A', status='available')
        self.booking = Booking.objects.create(
            user=self.renter, room=self.room, bed=self.bed,
            check_in=date(2026, 8, 1), status='confirmed',
            total_amount=2800, advance_paid=0,
        )
        self.settings = MealSettings.objects.create(
            hostel=self.hostel, is_enabled=True, default_status='on', cutoff_hours=6,
            rate_breakfast=60, rate_lunch=100, rate_dinner=90,
        )
        self.client = Client()

    # ---- helpers ---------------------------------------------------------
    def set_prefs(self, d, spec, locked=False):
        """spec: {'breakfast': 'on'|'off', ...} -> create MealPreference rows."""
        for meal_type, status in spec.items():
            MealPreference.objects.update_or_create(
                booking=self.booking, date=d, meal_type=meal_type,
                defaults={'status': status, 'is_locked': locked},
            )

    def prep(self, d, spec, locked=True):
        from hms import views
        self.set_prefs(d, spec, locked=locked)
        return views.generate_daily_meal_bill(self.booking, d)

    def patch_clock(self, y, mo, d, h, mi=0):
        """Patch hms.views time so all meal views see a fixed moment."""
        fake = _aware(y, mo, d, h, mi)
        return mock.patch('hms.views.timezone', mock.Mock(
            now=lambda: fake,
            localdate=lambda: fake.date(),
            localtime=lambda vt=None: fake,
        ))

    # ---- assert helpers --------------------------------------------------
    def load_my_bills(self):
        self.client.force_login(self.renter)
        resp = self.client.get('/meals/my-bills/')
        self.assertEqual(resp.status_code, 200)
        return resp.context


class ChargeableTotalTest(MealBillingTestBase):
    """Tests 1-5: Today's Total grows as each meal's cutoff passes."""

    # Window cheat-sheet (cutoff_hours=6): breakfast cutoff=1, lunch=6, dinner=13.
    # 00:00 -> none  | 03:00 -> breakfast  | 09:00 -> breakfast+lunch  | 15:00 -> all.

    def _total_at(self, spec, h, mi=0):
        target = date(2026, 8, 31)
        self.set_prefs(target, {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'})
        # override spec
        for mt, st in spec.items():
            mp = MealPreference.objects.get(booking=self.booking, date=target, meal_type=mt)
            mp.status = st
            mp.is_locked = False
            mp.save()
        with self.patch_clock(2026, 8, 31, h, mi):
            ctx = self.load_my_bills()
        return ctx['chargeable_total']

    def test_1_before_any_cutoff_total_0(self):
        self.assertEqual(self._total_at({}, 0, 30), 0)

    def test_2_after_breakfast_cutoff_only_60(self):
        self.assertEqual(self._total_at({}, 3), 60)

    def test_3_after_lunch_cutoff_160(self):
        self.assertEqual(self._total_at({}, 9), 160)

    def test_4_after_dinner_cutoff_250(self):
        self.assertEqual(self._total_at({}, 15), 250)

    def test_5_lunch_off_after_all_cutoffs_150(self):
        self.assertEqual(self._total_at({'lunch': 'off'}, 15), 150)


class AllOffAndNoStaleBillTest(MealBillingTestBase):
    """Tests 6 & 11: all-OFF day -> ৳0 and no payable bill; turning OFF reconciles."""

    def test_6_all_off_total_0_no_bill(self):
        target = date(2026, 8, 31)
        self.set_prefs(target, {'breakfast': 'off', 'lunch': 'off', 'dinner': 'off'})
        # Even if a stale paid-unpaid bill existed from a previous ON state:
        stale = MealBill.objects.create(
            booking=self.booking, date=target, breakfast_amount=60, lunch_amount=100,
            dinner_amount=90, total_amount=250, is_paid=False,
        )
        with self.patch_clock(2026, 8, 31, 15):
            ctx = self.load_my_bills()
        self.assertEqual(ctx['chargeable_total'], 0)
        self.assertEqual(ctx['today_status'], 'Unpaid')
        self.assertEqual(ctx['total_unpaid'], 0)
        # stale bill reconciled (removed/zeroed, not counted)
        self.assertFalse(
            MealBill.objects.filter(pk=stale.pk, is_paid=False, total_amount__gt=0).exists()
        )

    def test_11_lunch_turned_off_before_cutoff_never_charged(self):
        target = date(2026, 8, 31)
        # Renter had lunch ON, then turns it OFF before lunch cutoff; later the day progresses.
        self.set_prefs(target, {'breakfast': 'on', 'lunch': 'off', 'dinner': 'on'})
        # Simulate the day fully progressing past all cutoffs.
        with self.patch_clock(2026, 8, 31, 15):
            ctx = self.load_my_bills()
        self.assertEqual(ctx['today_meals']['lunch']['chargeable'], False)  # OFF is not chargeable
        self.assertEqual(ctx['today_meals']['lunch']['amount'], 0)
        self.assertEqual(ctx['chargeable_total'], 150)  # 60 + 0 + 90, NOT 250
        bill = MealBill.objects.filter(booking=self.booking, date=target).first()
        self.assertIsNotNone(bill)
        self.assertEqual(bill.lunch_amount, 0)
        self.assertEqual(bill.total_amount, 150)


class OutstandingBalanceTest(MealBillingTestBase):
    """Monthly outstanding: driven by locked+ON preferences across the month (OFF meals
    deducted), excludes future/unlocked days and stale rows, and is payable only after
    the month ends (next-day rule)."""

    def _aug_bucket(self, ctx):
        return ctx['monthly_unpaid'][0]

    def test_7_today_150_yesterday_250_outstanding_400(self):
        # Yesterday all-ON locked 250 + today lunch-OFF 150 => month total 400.
        yesterday = date(2026, 8, 30)
        self.prep(yesterday, {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        self.prep(date(2026, 8, 31), {'breakfast': 'on', 'lunch': 'off', 'dinner': 'on'}, locked=True)
        with self.patch_clock(2026, 8, 31, 18):
            ctx = self.load_my_bills()
        self.assertEqual(ctx['today_bill'].total_amount, 150)
        self.assertEqual(self._aug_bucket(ctx)['total'], 400)  # OFF lunch deducted
        self.assertEqual(ctx['total_unpaid'], 0)  # Aug not payable until Sep 1

    def test_8_future_bill_excluded_outstanding_250(self):
        today = date(2026, 8, 31)
        self.prep(today, {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)  # 250
        # Future (unlocked -> not counted) preference + a stale bill with no prefs.
        future = date(2026, 9, 1)
        future_bill = self.prep(future, {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=False)
        stale_date = date(2026, 8, 27)
        MealPreference.objects.filter(booking=self.booking, date=stale_date).delete()
        MealBill.objects.create(
            booking=self.booking, date=stale_date, breakfast_amount=60, lunch_amount=100,
            dinner_amount=90, total_amount=250, is_paid=False,
        )
        with self.patch_clock(2026, 8, 31, 18):
            ctx = self.load_my_bills()
        self.assertEqual(ctx['today_bill'].total_amount, 250)
        self.assertEqual(self._aug_bucket(ctx)['total'], 250)  # future/unlocked + stale excluded
        self.assertNotIn(future_bill, ctx['recent_bills'])  # future not shown

    def test_2500_regression_future_and_stale_excluded_no_dup(self):
        """10 all-ON locked days = ৳2500; future day + stale bill never double-count."""
        for d in [21, 24, 25, 26, 28, 29, 30]:
            self.prep(date(2026, 8, d), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        self.prep(date(2026, 8, 22), {'breakfast': 'on', 'lunch': 'off', 'dinner': 'on'}, locked=True)  # 150
        self.prep(date(2026, 8, 23), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)  # 250
        future = date(2026, 9, 5)
        self.prep(future, {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=False)  # excluded
        stale_date = date(2026, 8, 27)
        MealPreference.objects.filter(booking=self.booking, date=stale_date).delete()
        MealBill.objects.create(
            booking=self.booking, date=stale_date, breakfast_amount=60, lunch_amount=100,
            dinner_amount=90, total_amount=250, is_paid=False,  # stale, excluded
        )
        # Count locked+ON meals across the month (no duplicate, no future, no stale).
        expected = 7 * 250 + 150 + 250  # seven 250 days + 150 + 250 = 2150
        with self.patch_clock(2026, 8, 31, 18):
            ctx = self.load_my_bills()
        self.assertEqual(self._aug_bucket(ctx)['total'], expected)

    def test_all_paid_outstanding_0(self):
        # Settling a month removes it from outstanding.
        for d in [30, 31]:
            b = self.prep(date(2026, 8, d), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
            pay = Payment.objects.create(
                booking=self.booking, user=self.renter,
                transaction_id='T-M-{}-test'.format(d), amount=250,
                currency='BDT', status='success', payment_type='meal', payment_method='cod',
                metadata={'meal_month': '2026-08'},
            )
            b.payment = pay
            b.is_paid = True
            b.save(update_fields=['payment', 'is_paid'])
        with self.patch_clock(2026, 9, 1, 10):
            ctx = self.load_my_bills()
        self.assertEqual(ctx['total_unpaid'], 0)
        self.assertEqual(ctx['monthly_unpaid'], [])

    def test_payable_total_after_month_ends(self):
        """Once payable, the month's total is the outstanding balance."""
        self.prep(date(2026, 8, 1), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        self.prep(date(2026, 8, 2), {'breakfast': 'off', 'lunch': 'on', 'dinner': 'on'}, locked=True)  # 190
        with self.patch_clock(2026, 9, 1, 10):
            ctx = self.load_my_bills()
        self.assertEqual(ctx['total_unpaid'], 440)  # 250 + 190 payable
        self.assertTrue(self._aug_bucket(ctx)['payable'])


class FuturePaymentRejectTest(MealBillingTestBase):
    """Test 9: a future bill's payment is rejected with no Payment created."""

    def test_9_future_pay_rejected_no_payment(self):
        future = date(2026, 9, 1)
        # A future-dated bill should normally not exist (nothing locked yet), but if one
        # is present in the DB (e.g. stale row), a crafted pay request must be rejected
        # with NO Payment created.
        bill = MealBill.objects.create(
            booking=self.booking, date=future,
            breakfast_amount=60, lunch_amount=100, dinner_amount=90,
            total_amount=250, is_paid=False,
        )
        self.client.force_login(self.renter)
        before = Payment.objects.count()
        with self.patch_clock(2026, 8, 31, 18):
            resp = self.client.get(f'/meals/bills/{bill.pk}/pay/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/meals/my-bills/', resp.url)
        self.assertEqual(Payment.objects.count(), before)  # no Payment created


class SuccessfulPaymentTest(MealBillingTestBase):
    """Test 10: successful payment -> Paid, outstanding decreases, second attempt blocked."""

    def test_10_pay_flow_marks_paid_and_blocks_repay(self):
        today = date(2026, 8, 31)
        bill = self.prep(today, {'breakfast': 'on', 'lunch': 'off', 'dinner': 'on'}, locked=True)
        self.assertEqual(bill.total_amount, 150)
        payment = Payment.objects.create(
            booking=self.booking, user=self.renter, transaction_id='TXP-TEST-10',
            amount=bill.total_amount, currency='BDT', status='success',
            payment_type='meal', payment_method='sslcommerz',
        )
        bill.payment = payment
        bill.is_paid = True
        bill.save(update_fields=['payment', 'is_paid'])

        with self.patch_clock(2026, 8, 31, 18):
            ctx = self.load_my_bills()
        self.assertEqual(ctx['today_status'], 'Paid')
        self.assertEqual(ctx['total_unpaid'], 0)

        # Second payment attempt must be blocked (bill already paid -> 404 via is_paid filter).
        self.client.force_login(self.renter)
        resp = self.client.get(f'/meals/bills/{bill.pk}/pay/')
        self.assertEqual(resp.status_code, 404)


class MealPayDuplicateTest(MealBillingTestBase):
    """A bill must not get multiple in-flight payments from repeated clicks."""

    def test_no_shared_inflight_payment_across_bills(self):
        today = date(2026, 8, 31)
        past = date(2026, 8, 30)
        b_today = self.prep(today, {'breakfast': 'on', 'lunch': 'off', 'dinner': 'on'}, locked=True)
        b_past = self.prep(past, {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)

        # The view's reconcile must not let one payment back two bills.
        payment = Payment.objects.create(
            booking=self.booking, user=self.renter, transaction_id='TXP-SHARED',
            amount=b_today.total_amount, currency='BDT', status='processing',
            payment_type='meal', payment_method='sslcommerz',
        )
        b_today.payment = payment
        b_today.save(update_fields=['payment'])
        b_past.payment = payment
        b_past.save(update_fields=['payment'])

        with self.patch_clock(2026, 8, 31, 18):
            self.load_my_bills()  # triggers reconcile

        self.assertEqual(MealBill.objects.filter(payment=payment).count(), 1)


class ManagerMonitorTest(MealBillingTestBase):
    """Requirement 10: manager can see renter/date/amounts/status."""

    def test_manager_monitor_shows_bill_and_status(self):
        today = date(2026, 8, 31)
        self.prep(today, {'breakfast': 'on', 'lunch': 'off', 'dinner': 'on'}, locked=True)
        self.client.force_login(self.manager)
        with self.patch_clock(2026, 8, 31, 18):
            resp = self.client.get('/meals/payment-monitor/')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn(self.renter.full_name, html)
        self.assertIn('150', html)


class MonthlyPaymentTest(MealBillingTestBase):
    """Monthly billing: ONE payment per calendar month = locked+ON meals across the whole
    month (OFF meals deducted), payable only AFTER the month ends (next-day rule)."""

    def test_month_not_payable_during_month_so_outstanding_zero(self):
        """While August is still running (e.g. Aug 31), August is NOT payable and the
        payable outstanding balance is 0 (pay option arrives the day after Aug 31)."""
        self.prep(date(2026, 8, 21), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        self.prep(date(2026, 8, 22), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        with self.patch_clock(2026, 8, 31, 18):
            ctx = self.load_my_bills()
        self.assertEqual(ctx['total_unpaid'], 0)  # not payable yet
        self.assertEqual(len(ctx['monthly_unpaid']), 1)
        bucket = ctx['monthly_unpaid'][0]
        self.assertEqual((bucket['year'], bucket['month']), (2026, 8))
        self.assertEqual(bucket['total'], 500)  # full month of locked+ON meals
        self.assertFalse(bucket['payable'])
        self.assertEqual(bucket['payable_on'], date(2026, 9, 1))
        self.assertFalse(bucket['has_pending'])

    def test_month_payable_after_month_ends_and_off_meal_deducted(self):
        """On Sep 1 August is payable; an OFF meal is deducted from the monthly total."""
        self.prep(date(2026, 8, 1), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)     # 250
        self.prep(date(2026, 8, 2), {'breakfast': 'on', 'lunch': 'off', 'dinner': 'on'}, locked=True)    # 150
        with self.patch_clock(2026, 9, 1, 10):
            ctx = self.load_my_bills()
        self.assertEqual(ctx['total_unpaid'], 400)  # 250 + 150, lunch off deducted
        bucket = ctx['monthly_unpaid'][0]
        self.assertTrue(bucket['payable'])
        self.assertEqual(bucket['total'], 400)
        self.assertEqual(bucket['payable_on'], date(2026, 9, 1))

    def test_meal_pay_month_rejected_while_month_running(self):
        """Paying August is rejected before August ends (next-day rule); no Payment created."""
        self.prep(date(2026, 8, 21), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        self.client.force_login(self.renter)
        before = Payment.objects.count()
        with self.patch_clock(2026, 8, 31, 18):
            resp = self.client.get('/meals/pay-month/2026/8/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/meals/my-bills/', resp.url)
        self.assertEqual(Payment.objects.count(), before)

    def test_meal_pay_month_creates_single_tagged_payment_when_payable(self):
        """When payable, one tagged monthly Payment backs the whole month."""
        b1 = self.prep(date(2026, 8, 25), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        b2 = self.prep(date(2026, 8, 26), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        self.client.force_login(self.renter)
        with self.patch_clock(2026, 9, 1, 10), mock.patch('requests.post') as mpost:
            mpost.return_value.json.return_value = {
                'status': 'SUCCESS', 'GatewayPageURL': 'https://sandbox/x/1',
            }
            resp = self.client.get('/meals/pay-month/2026/8/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('sandbox', resp.url)
        payment = Payment.objects.get(metadata__meal_month='2026-08')
        self.assertEqual(payment.amount, 500)
        self.assertEqual(payment.status, 'processing')
        self.assertEqual(payment.payment_type, 'meal')
        for b in (b1, b2):
            b.refresh_from_db()
            self.assertEqual(b.payment, payment)
        self.assertEqual(MealBill.objects.filter(payment=payment).count(), 2)

    def test_meal_pay_month_reuses_inflight_payment_on_repeat(self):
        """A repeated request reuses the same in-flight monthly payment (no duplicate)."""
        self.prep(date(2026, 8, 25), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        self.prep(date(2026, 8, 26), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        self.client.force_login(self.renter)
        with self.patch_clock(2026, 9, 1, 10), mock.patch('requests.post') as mpost:
            mpost.return_value.json.return_value = {'status': 'SUCCESS', 'GatewayPageURL': 'https://sandbox/x/1'}
            self.client.get('/meals/pay-month/2026/8/')
            self.client.get('/meals/pay-month/2026/8/')
        self.assertEqual(Payment.objects.filter(metadata__meal_month='2026-08').count(), 1)

    def test_monthly_success_marks_all_month_bills_paid_and_settles(self):
        """Settling the monthly payment marks every unpaid bill of that month paid."""
        b1 = self.prep(date(2026, 8, 25), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        b2 = self.prep(date(2026, 8, 26), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        payment = Payment.objects.create(
            booking=self.booking, user=self.renter, transaction_id='MONTH-TEST',
            amount=500, currency='BDT', status='pending', payment_type='meal',
            metadata={'meal_month': '2026-08'},
        )
        for b in (b1, b2):
            b.payment = payment
            b.save(update_fields=['payment'])
        from hms.views import _mark_payment_success
        _mark_payment_success(payment, val_id='VALID1')
        for b in (b1, b2):
            b.refresh_from_db()
            self.assertTrue(b.is_paid)
        self.assertEqual(MealBill.objects.filter(payment=payment, is_paid=False).count(), 0)
        # A settled month no longer appears as outstanding.
        with self.patch_clock(2026, 9, 1, 10):
            ctx = self.load_my_bills()
        self.assertEqual(ctx['total_unpaid'], 0)
        self.assertEqual(ctx['monthly_unpaid'], [])

    def test_monthly_payment_preserved_not_detangled(self):
        """A tagged monthly payment may span multiple bills; reconcile must keep it intact."""
        b1 = self.prep(date(2026, 8, 25), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        b2 = self.prep(date(2026, 8, 26), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        payment = Payment.objects.create(
            booking=self.booking, user=self.renter, transaction_id='MONTH-KEEP',
            amount=500, currency='BDT', status='processing', payment_type='meal',
            metadata={'meal_month': '2026-08'},
        )
        for b in (b1, b2):
            b.payment = payment
            b.save(update_fields=['payment'])
        with self.patch_clock(2026, 9, 1, 10):
            self.load_my_bills()  # triggers reconcile
        self.assertEqual(MealBill.objects.filter(payment=payment).count(), 2)

    def test_stale_untagged_inflight_does_not_block_month_pay(self):
        """A leftover untagged per-day processing payment must NOT hide the month Pay button."""
        b1 = self.prep(date(2026, 8, 25), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        b2 = self.prep(date(2026, 8, 26), {'breakfast': 'on', 'lunch': 'on', 'dinner': 'on'}, locked=True)
        stale = Payment.objects.create(
            booking=self.booking, user=self.renter, transaction_id='STALE-ONLY',
            amount=250, currency='BDT', status='processing', payment_type='meal',
        )
        b1.payment = stale
        b1.save(update_fields=['payment'])
        with self.patch_clock(2026, 9, 1, 10):
            ctx = self.load_my_bills()
        bucket = ctx['monthly_unpaid'][0]
        self.assertFalse(bucket['has_pending'])  # untagged stale does not block Pay
        self.assertEqual(bucket['total'], 500)
