from openerp.osv import osv,fields
from openerp import api
from openerp.tools.translate import _
from datetime import datetime, timedelta, date
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from openerp import SUPERUSER_ID

class account_invoice(osv.osv):
	_inherit = 'account.invoice'

	_columns = {
		'member_id': fields.many2one('membership.point.member','Member ID', domain=[('member_type','=','personal')], ondelete="set null"),
		'institution_id': fields.many2one('membership.point.member','Institution', domain=[('member_type','=','institution')], ondelete="set null"),
	}

	@api.model
	def calculate_invoice_point(self, member, invoice_line):
	# to be overridden by inheriting module
		return None

	@api.multi
	def post_point_log(self):
		member_obj = self.pool.get('membership.point.member')
		log_obj = self.pool.get('membership.point.log')
	# hitung dan post point log ketika invoice di-validate
		for invoice in self:
		# tentukan member_id. kalau individual maka pakai member_id, tapi kalau setelah diset
		# ternyata institution_id nya ada, institution yang dapet point
		# hanya proses invoice yang ada membernya
			if not (invoice.member_id or invoice.institution_id): continue
			member_id = None
			if invoice.member_id: member_id = invoice.member_id.id
			if invoice.institution_id: member_id = invoice.institution_id.id
			member = member_obj.browse(self.env.cr, self.env.uid, member_id)
		# pastikan point hanya digenerate satu kali
			point_log_ids = log_obj.search(self.env.cr, self.env.uid, [('invoice_id','=',invoice.id)])
			if len(point_log_ids) > 0: continue
		# untuk setiap line invoice...
			total_points = 0
			first_product = None
			for line in invoice.invoice_line:
				if not first_product: first_product = line.product_id.name
				line_point = self.calculate_invoice_point(member, line)
				if line_point == None: 
					raise osv.except_osv(_('Point Calculation Error'),_('Calculation error: calculate_member_point is not implemented in custom module.'))
				total_points += line_point
		# masukkan point lognya
			if total_points > 0:
				name = _('Invoice %s') % (invoice.internal_number and invoice.internal_number or invoice.name)
				if first_product:
					name += ' (%s)' % first_product
				log_obj.create(self.env.cr, self.env.uid, {
					'member_id': member.id,
					'invoice_id': invoice.id,
					'name': name,
					'point_in': total_points,
					'level': member.current_level.name,
					'type': 'generate',
					})

	@api.multi
	def invoice_validate(self):
	# insert point log untuk invoice ini
		self.post_point_log()
		return super(account_invoice, self).invoice_validate()

	@api.multi
	def action_cancel(self):
	# hapus point log terkait invoice ini
		log_obj = self.pool.get('membership.point.log')
		point_log_ids = log_obj.search(self.env.cr, self.env.uid, [('invoice_id','in',self.ids)])
		log_obj.unlink(self.env.cr, self.env.uid, point_log_ids)
		return super(account_invoice, self).action_cancel()

	@api.multi
	def confirm_paid(self):
		super(account_invoice, self).confirm_paid()
	# confirm member point
		point_obj = self.pool.get('membership.point.log')
		for invoice in self:
		# ambil point log yang invoice nya ini. karena satu invoice = satu log, sudah bisa dipastikan 
		# cukup ambil invoice_ids yang pertama
			point_ids = point_obj.search(self.env.cr, self.env.uid, [('invoice_id','=',invoice.id)])
			if len(point_ids) > 0:
				point_obj.action_approve(self.env.cr, self.env.uid, point_ids)
		
