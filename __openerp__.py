{
	'name': 'Membership Point System',
	'version': '1.0',
	'author': 'Christyan Juniady and Associates',
	'maintainer': 'Christyan Juniady and Associates',
	'category': 'General',
	'sequence': 21,
	'website': 'http://www.chjs.biz',
	'summary': '',
	'description': """
			Membership point system with possibility of level-based membership system (e.g. Silver, Gold, Platinum).
			Members can automatically upgrade their level based on the number of points collected.
			Members can also use points to purchase something, and this module has provided methods 
			to register point use as well as point addition.
	""",
	'author': 'Christyan Juniady and Associates',
	'images': [
	],
	'depends': ['base','web','mail','chjs_dated_setting','account'],
	'data': [
		'views/membership_point.xml',
		'views/membership_promo.xml',
		'views/account_invoice.xml',
	],
	'demo': [
	],
	'test': [
	],
	'installable': True,
	'application': False,
	'auto_install': False,
	'qweb': [
	 ],
}