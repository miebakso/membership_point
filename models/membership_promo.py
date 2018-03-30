import datetime
from dateutil.relativedelta import relativedelta
from openerp import models, fields, api
from openerp.exceptions import ValidationError
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT

# ==========================================================================================================================

class membership_point_welcome_promo(models.Model):
	_name =  "membership.point.welcome.promo"
	_inherit = "chjs.dated.setting"
	_description = "Membership point welcome promo"

	welcome_point = fields.Float('Welcome Point', required=True)

# ==========================================================================================================================

class membership_point_voucher_setting(models.Model):
	_name = 'membership.point.voucher.setting'
	_description = 'Setting for membership point voucher'

	name = fields.Char('Voucher Name', size=255, required=True)
	description = fields.Text('Voucher Description')
	terms_and_conditions = fields.Text('Voucher Terms and Conditions')
	thumbnail = fields.Binary('Voucher Thumbnail')
	voucher_image = fields.Binary('Voucher Image')
	voucher_type = fields.Selection([
		('member', 'Member'),
		('gift', 'Gift'),
	], 'Voucher Type', required=True, default='member')
	is_purchaseable = fields.Boolean('Is Voucher Purchaseable?', default=True)
	point_price = fields.Float('Voucher Price (in points)')
	member_level_ids = fields.Many2many('membership.point.level', 'membership_voucher_setting_level_rel', 'voucher_setting_id', 'level_id', 'Member Levels')
	expire_calculation = fields.Selection([
		('month', 'Month'),
		('specific_date', 'Specific Date'),
	], 'Voucher Expire Calculation Method', default='month')
	expired_date = fields.Date('Voucher Expire Date')
	expired_month = fields.Integer('Voucher Expire Month')
	generated_count = fields.Integer('Number of Vouchers Generated', compute="_compute_count", store=False)
	active_count = fields.Integer('Number of Vouchers Active', compute="_compute_count", store=False)
	used_count = fields.Integer('Number of Vouchers Used', compute="_compute_count", store=False)
	expired_count = fields.Integer('Number of Vouchers Expired', compute="_compute_count", store=False)

	@api.one
	def purchase_member_voucher(self, member, qty):
		cost = self.point_price * qty
		if member.current_point < cost:
			raise ValidationError('Member doesn\'t have sufficient point.')

		create_voucher = qty
		while create_voucher > 0:
			self.env['membership.point.voucher'].create({
				'setting_id': self.setting_id,
				'member_id': member.id,
			})
			create_voucher -= 1
		
		self.env['membership.point.log'].create({
			'create_date': datetime.date.today(),
			'member_id': member.id,
			'name': ('Voucher purchase of %d x %s (@ %d points)' % (qty, self.name, self.point_price)),
			'type': 'usage',
		})

	@api.multi
	def _compute_count(self):
		voucher_env = self.env['membership.point.voucher']
		for record in self:
			record.generated_count = len(voucher_env.search([('setting_id','=',record.id),('state','=','generated')]))
			record.used_count = len(voucher_env.search([('setting_id','=',record.id),('state','=','used')]))
			record.expired_count = len(voucher_env.search([('setting_id','=',record.id),('state','=','expired')]))
			record.active_count = len(voucher_env.search([('setting_id','=',record.id)])) - (record.generated_count + record.used_count + record.expired_count)

# ==========================================================================================================================

class membership_point_voucher(models.Model):
	_name = 'membership.point.voucher'
	_description = 'Membership point voucher'

	name = fields.Char('Voucher Number', size=100, required=True)
	description = fields.Char('Voucher Name', size=255, compute="_compute_description", store=False)
	member_id = fields.Many2one('membership.point.member', 'Voucher Owner')
	setting_id = fields.Many2one('membership.point.voucher.setting', 'Voucher Setting')
	state = fields.Selection([
		('generated', 'Generated'),
		('used', 'Used'),
		('expired', 'Expired'),
	], 'Voucher State', required=True, default='generated')
	usage_date = fields.Datetime('Voucher Usage Date')
	usage_by = fields.Many2one('res.users', 'Usage by', ondelete='set null')
	expired_date = fields.Date('Voucher Expire Date', required=True)

	@api.one
	def action_use_voucher(self):
		self.write({
			'usage_date': datetime.datetime.now(),
			'usage_by': self._uid,
			'state': 'used',
		})

	def generate_number(self, vals):
		return ""

	@api.model
	def create(self, vals):
		generated_number = self.generate_number(vals)
		if generated_number == "":
			raise ValidationError('Voucher number isn\'t generated, probably because generate_number() function is not yet implemented.')

		voucher_setting = self.env['membership.point.voucher.setting'].browse(vals['setting_id'])[0]
		if voucher_setting.voucher_type == 'member':
			member = self.env['membership.point.member'].browse(vals['member_id'])[0]
			flg1 = False
			if len(voucher_setting.member_level_ids) == 0:
				flg1 = True
			else:
				for available_member_level in voucher_setting.member_level_ids:
					for member_level in member.current_level:
						if available_member_level == member_level:
							flg1 = True
							break
					if flg1:
						break

			if not flg1:
				raise ValidationError('Member doesn\'t have the level required.')

		vals['name'] = generated_number
		vals['expired_date'] = {
			'specific_date': voucher_setting.expired_date,
			'month': datetime.date.today() + relativedelta(months = +voucher_setting.expired_month),
		}[voucher_setting.expire_calculation]

		return super(membership_point_voucher, self).create(vals)

	@api.multi
	def _compute_description(self):
		voucher_setting_env = self.env['membership.point.voucher.setting']
		for record in self:
			record.description = voucher_setting_env.browse(record.setting_id.id).name

	@api.model
	def cron_autoexpire_voucher(self):
		vouchers = self.search([('state','!=','expired')])
		for voucher in vouchers:
			if datetime.datetime.strptime(voucher.expired_date, DEFAULT_SERVER_DATE_FORMAT).date() >= datetime.date.today():
				voucher.write({
					'state': 'expired',
				})

# ==========================================================================================================================

class membership_point_voucher_generate(models.Model):
	_name = 'membership.point.voucher.generate'
	_description = 'History/log generate gift voucher'

	setting_id = fields.Many2one('membership.point.voucher.setting', 'Voucher Setting', domain="[('voucher_type','=','gift')]")
	number_of_vouchers = fields.Integer('Number of Voucher Generated', required=True, default=1)
	unit_cost = fields.Float('Unit Cost')
	total_cost = fields.Float('Total Cost', compute="_compute_cost", store=False)
	state = fields.Selection([
		('draft', 'Draft'),
		('confirmed', 'Confirmed'),
		('rejected', 'Rejected'),
	], default='draft')

	@api.one
	def action_confirm(self):
		self.write({
			'state': 'confirmed',
		})

		generate = self.number_of_vouchers
		while generate > 0:
			self.env['membership.point.voucher'].create({
				'setting_id': self.setting_id.id,
			})
			generate -= 1

	@api.one
	def action_reject(self):
		self.write({
			'state': 'rejected',
		})

	@api.multi
	def _compute_cost(self):
		for record in self:
			record.total_cost = record.unit_cost * record.number_of_vouchers