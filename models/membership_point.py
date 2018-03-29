from openerp.osv import osv,fields
from openerp.tools.translate import _
from datetime import datetime, timedelta, date
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from openerp import SUPERUSER_ID
import re

LOG_PER_PAGE = 20

POINT_LOG_STATE = (
	('draft','Draft'),
	('confirmed','Confirmed'),
	('rejected','Rejected'),
	('expired','Expired'),
	)

# ==========================================================================================================================

class membership_point_level(osv.osv):

	_name = 'membership.point.level'
	_description = 'Membership point levels'

	_columns = {
		'name': fields.char('Level Name', required=True),
		'sequence': fields.integer('Sequence', required=True),
		'notes': fields.text('Level Privileges'),
	}

	_sql_constraints = [
		('name_unique', 'UNIQUE(name)', _('Name must be unique.')),
		('sequence_unique', 'UNIQUE(sequence)', _('Sequence must be unique.')),
	]

	_order = 'sequence, id'

# ==========================================================================================================================

class membership_point_setting(osv.osv):

	_name = 'membership.point.setting'
	_inherit = 'chjs.dated.setting'
	_description = 'Membership point setting'

	_columns = {
		'level_settings': fields.one2many('membership.point.setting.level', 'header_id', string="Level Settings"),
	}

	def _default_level_settings(self, cr, uid, context=None):
	# ambil master level sesuai urutannya
		level_obj = self.pool.get('membership.point.level')
		level_ids = level_obj.search(cr, uid, [])
		result = []
		for row in level_obj.browse(cr, uid, level_ids):
			result.append({
				'membership_level_id': row.id,
				})
		return result

	_defaults = {
		'level_settings': _default_level_settings,
	}

	def determine_level_by_point(self, cr, uid, setting, points):
		if not setting: setting = self.get_current(cr, uid)
		for level in reversed(setting.level_settings):
			if points >= level.minimum_point:
				return level.membership_level_id.id
		return setting.level_settings[0].membership_level_id.id

# ==========================================================================================================================

class membership_point_setting_level(osv.osv):

	_name = 'membership.point.setting.level'
	_description = 'Membership point setting line'

	_columns = {
		'header_id': fields.many2one('membership.point.setting', 'Header'),
		'membership_level_id': fields.many2one('membership.point.level', string='Level', required=True),
		'minimum_point': fields.integer('Minimum Point', required=True,
			help='Minimum accumulated points to upgrade to this level. If usage is such that accumulated points decreases to under minimum point, the member is automatically downgraded to level under this one.'),
	}

	_order = "header_id,minimum_point"

# ==========================================================================================================================

class membership_point_member(osv.osv):

	_name = 'membership.point.member'
	_description = 'Membership data'
	_inherit = ['mail.thread']

	def _current_point_and_level(self, cr, uid, ids, fields, arg, context={}):
		result = {}
	# ambil data sum point dulu
		point_log_obj = self.pool.get('membership.point.log')
		#point_log_ids = point_log_obj.search(cr, uid, [('state','=','confirmed'),('member_id','in',ids)])
		cr.execute("""
			SELECT member_id, (SUM(point_in) - SUM(point_out)) as current_point
			FROM membership_point_log
			WHERE state='confirmed' AND member_id IN (%s)
			GROUP BY member_id
		""" % ",".join([str(sid) for sid in ids]))
		member_point = {}
		for sid in ids: member_point.update({sid: 0})
		for row in cr.dictfetchall():
			member_point.update({row['member_id']: row['current_point']})
	# ambil settingan level
		point_setting_obj = self.pool.get('membership.point.setting')
		setting = point_setting_obj.get_current(cr, uid)
	# mulai pasangin
		for row in self.browse(cr, uid, ids, context=context):
			result[row.id] = {
				'current_point': member_point.get(row.id, 0),
				'current_level': point_setting_obj.determine_level_by_point(cr, uid, setting, member_point.get(row.id, None)),
			}
		return result

	_columns = {
		'member_id': fields.char(size=20, string="Member ID", readonly=True),
		'name': fields.char('First Name/Institution Name', required=True, size=255),
		'last_name': fields.char('Last Name', size=255),
		'email': fields.char('Email Address', required=True),
		'id_number': fields.char('ID No.', size=100),
		'partner_id': fields.many2one('res.partner', string='Related Customer',
			domain=[('customer','=',True)], track_visibility='onchange'),
		'street': fields.char('Address Line 1'),
		'street2': fields.char('Address Line 2'),
		'zip': fields.char('Postal Code'),
		'phone': fields.char('Phone'),
		'city': fields.char('City'),
		'mobile': fields.char('Mobile Phone'),
		'birth_date': fields.date('Birth Date'),
		'register_type': fields.selection((
			('self_enroll','Self Enrollment'),
			('manual','Manual Enrollment'),
			), string="Register Type", readonly=True),
		'register_date': fields.date('Register Date', required=True),
		'current_point': fields.function(_current_point_and_level, string="Current Point",
			multi="current_point", type="integer", method=True),
		'current_level': fields.function(_current_point_and_level, string="Current Level",
			multi="current_point", type="many2one", relation="membership.point.level", method=True),
		'register_level': fields.many2one('membership.point.level', string='Register Level',
			help='The level selected when this member was first registered.', ondelete="restrict"),
		'state': fields.selection((
				('draft','Pending'),
				('registered','Registered'),
				('suspended','Suspended'),
				('terminated','Terminated'),
			), string='State', readonly=True, track_visibility='onchange'),
		'point_logs': fields.one2many('membership.point.log', 'member_id', 'Point History', readonly=True),
		'member_type': fields.selection((
			('personal','Personal'),
			('institution','Institution'),
			), 'Member Type'),
		'institution_members': fields.one2many('membership.point.institution.member', 'institution_id', 'Institution Members'),
	}

	def _default_register_level(self, cr, uid, context={}):
	# ambil level terbawah yang berlaku
		point_level_obj = self.pool.get('membership.point.level')
		point_level_ids = point_level_obj.search(cr, uid, [], order="sequence,id")
		return point_level_ids and point_level_ids[0] or None

	_defaults = {
		'register_type': 'manual',
		'state': 'draft',
		'register_date': lambda *a: datetime.today().strftime(DEFAULT_SERVER_DATE_FORMAT),
		'register_level': _default_register_level,
		'member_type': 'personal',
	}

	def _constraint_email(self, cr, uid, ids, context={}):
		for member in self.browse(cr, uid, ids):
			if re.match("^[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,4})$", member.email) == None:
				return False
		return True

	def _constraint_email_unique(self, cr, uid, ids, context={}):
		for member in self.browse(cr, uid, ids):
			check_ids = self.search(cr, uid, [('email','=',member.email),('id','!=',member.id)])
			if len(check_ids) > 0:
				return False
		return True

	_constraints = [
		(_constraint_email,_('Invalid email format.'),['email']),
		(_constraint_email_unique,_('There is already another member registered with this email address. Please use another.'),['email']),
	]

	_sql_constraints = [
		('member_id_unique', 'UNIQUE(member_id)', _('Member ID must be unique.')),
	]

	def generate_member_id(self, cr, uid, member):
		return "" # harus diimplement di modul customnya

	def create_member_user(self, cr, uid, member):
		user_obj = self.pool.get('res.users')
	# bikin user baru
	# user harus dilink ke partner member ini
		if not (member.partner_id and member.name and member.email):
			raise osv.except_osv(_('Member Error'),_('Please fill in Customer, Name, and Email Address.'))
	# ambil group portal, ke mana user ybs akan diassign
		dataobj = self.pool.get('ir.model.data')
		dummy, group_id = dataobj.get_object_reference(cr, SUPERUSER_ID, 'base', 'group_portal')
		new_user_id = user_obj.create(cr, uid, {
			'name': self.get_member_fullname(member),
			'login': member.email,
			'password': member.password or member.email, # sementara
			'partner_id': member.partner_id.id,
			'groups_id': [(6,0,[group_id])],
			})
		return new_user_id

	def get_member_by_uid(self, cr, uid, user_id, context={}):
	# apakah user user_id adalah member?
	# kuncinya, cari member yang partner id nya idem user tsb
		user_data = self.pool.get('res.users').browse(cr, uid, user_id)
		if not user_data: return False
		user_partner_id = user_data.partner_id.id
		member_ids = self.search(cr, uid, [('partner_id','=',user_partner_id)])
		return len(member_ids) > 0 and self.browse(cr, uid, member_ids[0]) or None

	def get_user_by_member_id(self, cr, uid, member_id, context={}):
		member_data = self.browse(cr, uid, member_id)
		if not member_data: return False
		member_partner_id = member_data.partner_id.id
		user_obj = self.pool.get('res.users')
		user_ids = user_obj.search(cr, uid, [('partner_id','=',member_partner_id)])
		return len(user_ids) > 0 and user_obj.browse(cr, uid, user_ids[0]) or None

	def get_member_fullname(self, member):
		return "%s%s" % (member.name,member.last_name and ' '+member.last_name or '')

	def action_activate(self, cr, uid, ids, context={}):
		partner_obj = self.pool.get('res.partner')
		for member in self.browse(cr, uid, ids, context=context):
		# generate member id
			member_id = self.generate_member_id(cr, uid, member)
			if not member_id:
				raise osv.except_osv(_('Member Error'),_('Auto-generate member ID has not been implemented.'))
			self.write(cr, uid, [member.id], {
				'state': 'registered',
				'member_id': member_id,
			})
		# bikin user baru
			self.create_member_user(cr, uid, member)
		# update nama partner sesuai registrasi
			partner_obj.write(cr, uid, [member.partner_id.id], {
				'name': self.get_member_fullname(member),
				'email': member.email,
				})

			obj_promo = self.pool.get('membership.point.welcome.promo')												# PROSI
			promos = obj_promo.browse(cr, uid, obj_promo.search(cr, uid, []))										# PROSI
			first = True																							# PROSI
			get_promo = False																						# PROSI
			for promo in promos:
				reg_date = datetime.strptime(member.register_date, DEFAULT_SERVER_DATE_FORMAT)						# PROSI
				val_from = datetime.strptime(promo.valid_from, DEFAULT_SERVER_DATE_FORMAT)							# PROSI

				if promo.valid_through != False:																	# PROSI
					val_through = datetime.strptime(promo.valid_through, DEFAULT_SERVER_DATE_FORMAT)				# PROSI
					if reg_date >= val_from and reg_date <= val_through:											# PROSI
						if first:																					# PROSI
							get_promo = promo																		# PROSI
							first = False																			# PROSI
						else:																						# PROSI
							if val_from < datetime.strptime(get_promo.valid_from, DEFAULT_SERVER_DATE_FORMAT):		# PROSI
								get_promo = promo																	# PROSI
				else:
					if reg_date >= val_from:																		# PROSI
						if first:																					# PROSI
							get_promo = promo																		# PROSI
							first = False																			# PROSI
						else:																						# PROSI
							if val_from < datetime.strptime(get_promo.valid_from, DEFAULT_SERVER_DATE_FORMAT):		# PROSI
								get_promo = promo																	# PROSI

			if get_promo:																							# PROSI
				point_log = self.pool.get("membership.point.log")													# PROSI
				values = {																							# PROSI
					'type': 'welcome',																				# PROSI
					'name': 'Welcome promo points',																	# PROSI
					'member_id': member.id,																			# PROSI
					'point_in': get_promo.welcome_point																# PROSI
				}																									# PROSI
				log_id =point_log.create(cr,uid,values)																# PROSI
				point_log.action_approve(cr,uid,log_id)																# PROSI

		return True

	def action_suspend(self, cr, uid, ids, context={}):
		user_obj = self.pool.get('res.users')
		for member in self.browse(cr, uid, ids, context=context):
			user_ids = user_obj.search(cr, uid, [('partner_id','=',member.partner_id.id)])
			user_obj.write(cr, uid, user_ids, {'active': False})
		return self.write(cr, uid, ids, {
			'state': 'suspended',
			})

	def action_terminate(self, cr, uid, ids, context={}):
		user_obj = self.pool.get('res.users')
		for member in self.browse(cr, uid, ids, context=context):
			user_ids = user_obj.search(cr, uid, [('partner_id','=',member.partner_id.id)])
			user_obj.write(cr, uid, user_ids, {'active': False})
		return self.write(cr, uid, ids, {
			'state': 'terminated',
			})

	def action_reactivate(self, cr, uid, ids, context={}):
		user_obj = self.pool.get('res.users')
		for member in self.browse(cr, uid, ids, context=context):
			user_ids = user_obj.search(cr, uid, [('partner_id','=',member.partner_id.id),('active','=',False)])
			user_obj.write(cr, uid, user_ids, {'active': True})
		return self.write(cr, uid, ids, {
			'state': 'registered',
			})

	def validate_inputs(self, cr, uid, vals):
	# cek email unik dan format email
	# terpaksa dilakukan di sini karena menggunakan framework 8 kalau create dipanggil
	# dari controller maka insertion udah keburu dilakukan dan ketika constraint dicek
	# dan gagal maka operasi tidak di-rollback
	# email harus format bener
		email = vals.get('email', False)
		if not email:
			raise osv.except_osv(_('Member Error'), _('Please provide email when registering member.'))
		if re.match("^[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,4})$", email) == None:
			raise osv.except_osv(_('Member Error'), _('Invalid email format.'))
		check_ids = self.search(cr, uid, [('email','=',email)])
		if len(check_ids) > 0:
			raise osv.except_osv(_('Member Error'), _('There is already another member registered with this email address. Please use another.'))

	def create(self, cr, uid, vals, context={}):
		self.validate_inputs(cr, uid, vals)
		new_id = super(membership_point_member, self).create(cr, uid, vals, context=context)
		if context.get('manual_register', False):
			self.action_activate(cr, uid, [new_id], context=context)
		return new_id

	def name_search(self, cr, uid, name='', args=None, operator='ilike', context=None, limit=100):
	# search juga bisa dilakukan dengan mengetikkan nomor member
		if not args: args = []
		if name:
			ids = self.search(cr, uid, ['|',('name','ilike',name),('member_id','ilike',name)]+args, limit=limit,
			context=context)
		else:
			ids = self.search(cr, uid, args, limit=limit, context=context)
		result = self.name_get(cr, uid, ids, context=context)
		return result

	def name_get(self, cr, uid, ids, context={}):
		if not ids: return []
		if isinstance(ids, (int, long)): ids = [ids]
		result = []
		for record in self.browse(cr, uid, ids):
			if record.member_id:
				label = "%s %s%s" % (record.member_id,record.name,(record.last_name and ' '+record.last_name or ''))
			else:
				label = "%s%s" % (record.name,(record.last_name and ' '+record.last_name or ''))
			result.append((record['id'], label))
		return result

# ==========================================================================================================================

class membership_point_institution_member(osv.osv):

	_name = 'membership.point.institution.member'
	_description = 'Members of institution member type'

	_columns = {
		'institution_id': fields.many2one('membership.point.member', 'Institution'),
		'member_id': fields.many2one('membership.point.member', 'Member'),
	}

# ==========================================================================================================================

class membership_point_log(osv.osv):

	_name = 'membership.point.log'
	_description = 'Member point log (usage and addition)'

	_columns = {
		'create_date': fields.datetime('Log Date', required=True),
		'member_id': fields.many2one('membership.point.member', string="Member", required=True, ondelete="cascade"),
		'name': fields.char('Transaction Reference', size=255),
		'point_in': fields.integer('Addition'),
		'point_out': fields.integer('Usage'),
		'level': fields.char('Level when Logged', readonly=True), # sengaja char supaya kalo level udah dihapus pun di sini masih muncul
		'type': fields.selection((
				('generate','Addition'),
				('usage','Usage'),
				('welcome','Welcome Bonus'),
				('manual','Manual Input'),
			), string="Log Type"),
		'notes': fields.text('Notes'),
		'state': fields.selection(POINT_LOG_STATE, string='State'),
		'invoice_id': fields.many2one('account.invoice', 'Invoice', readonly=True, ondelete="cascade"),
	}

	_defaults = {
		'create_date': lambda *a: datetime.today().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
		'point_in': 0,
		'point_out': 0,
		'type': 'manual',
		'state': 'draft',
	}

	def action_approve(self, cr, uid, ids, context={}):
		return self.write(cr, uid, ids, {
			'state': 'confirmed',
			})

	def action_reject(self, cr, uid, ids, context={}):
		return self.write(cr, uid, ids, {
			'state': 'rejected',
			})

	def _additional_log_detail(self, cr, uid, line, log_data):
	# bisa dioverride untuk menambah field2 detail di log line nya
		return line

	def get_log_by_member(self, cr, uid, member_id, page=1, order='create_date DESC', domain=[], formatted=True):
		offset = max(page-1,0) * LOG_PER_PAGE
		limit = LOG_PER_PAGE
		domain = [('member_id','=',member_id)] + domain
		log_ids = self.search(cr, uid, domain, offset=offset, limit=limit, order=order)
		if formatted:
			result = []
			for row in self.browse(cr, uid, log_ids):
				create_date = datetime.strptime(row.create_date, DEFAULT_SERVER_DATETIME_FORMAT)
				create_date = create_date.strftime("%A, %d %B %Y")
				point = "+%s points" % int(row.point_in) if row.point_in > 0 else "-%s points" % int(row.point_out)
				line = {
					'log_id': row.id,
					'date': create_date,
					'description': row.name,
					'point': point,
					'state': dict(POINT_LOG_STATE).get(row.state),
				}
				line = self._additional_log_detail(cr, uid, line, row)
				result.append(line)
			return result
		else:
			return self.browse(cr, uid, log_ids)


	def create(self, cr, uid, vals, context={}):
		new_id = super(membership_point_log, self).create(cr, uid, vals, context=context)
		new_data = self.browse(cr, uid, new_id)
		self.write(cr, uid, [new_id], {
			'level': new_data.member_id.current_level.name,
			})
		if context.get('manual_point', False):
			self.action_approve(cr, uid, [new_id])
		return new_id
