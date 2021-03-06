# -*- coding: utf-8 -*-

from openerp import models, fields, api, _
from openerp.exceptions import except_orm, ValidationError
from openerp.osv import osv
import urllib2, httplib, urlparse, gzip, requests, json
from StringIO import StringIO
import openerp.addons.decimal_precision as dp
import logging
from datetime import date
import ast
#Get the logger
_logger = logging.getLogger(__name__)

class cash_register_transfer_wizard(models.TransientModel):
	_name = 'cash.register.transfer.wizard'

	@api.multi
	def transfer_cash_register(self):
		#if self.session_id.id == self.destination_session_id.id:
		#	raise ValidationError('La caja destino no puede ser igual a la caja origen')
		session = self.session_id
		destination_session = self.destination_session_id
		credit_account_id = session.config_id.cash_journal.default_debit_account_id.id
		credit_account = session.config_id.cash_journal.default_debit_account_id
		if self.amount > credit_account.balance:
			raise ValidationError('El monto ingresado no puede superar el saldo de la caja')
		vals = {}
		for dest_statement in destination_session.statement_ids:
			if dest_statement.journal_id.id == destination_session.config_id.cash_journal.id:
				vals_destination = {
					'statement_id': dest_statement.id,
					'ref': 'Rec.Deposito ' + session.name,
					'name': 'Rec.Deposito ' + destination_session.name,
					'amount': self.amount,
					'date': str(date.today()),
					}
		if vals_destination:
			statement_line = self.env['account.bank.statement.line'].create(vals_destination)		
		for statement in session.statement_ids:
			if statement.journal_id.id == session.config_id.cash_journal.id:
				vals = {
					'statement_id': statement.id,
					'ref': 'Deposito ' + session.name,
					'name': 'Deposito ' + session.name,
					'amount': self.amount * (-1),
					'date': str(date.today()),
					}
		if not vals:
			raise ValidationError('Problemas en la configuración de la sesión')
		if vals:
			statement_line = self.env['account.bank.statement.line'].create(vals)		
		vals = {
			'name': self.name,
			'user_id': self.user_id.id,
			'session_id': self.session_id.id,
			'date': self.date,
			'statement_line_id': statement_line.id,
			'amount': self.amount
			}
		return_id = self.env['pos.session.transfer'].create(vals)
	
	name = fields.Char('Nombre')
	user_id = fields.Many2one('res.users')
	session_id = fields.Many2one('pos.session',domain=[('state','=','opened')])
	destination_session_id = fields.Many2one('pos.session',string='Caja Destino',domain=[('state','=','opened')])
	date = fields.Date('Fecha')
	amount = fields.Float('Monto')

class bank_deposit_pdv(models.TransientModel):
	_name = 'bank.deposit.pdv'

	@api.multi
	def create_deposit(self):
		session = self.session_id
		credit_account_id = session.config_id.cash_journal.default_debit_account_id.id
		credit_account = session.config_id.cash_journal.default_debit_account_id
		if self.amount > credit_account.balance:
			raise ValidationError('El monto ingresado no puede superar el saldo de la caja')
		for statement in session.statement_ids:
			if statement.journal_id.id == session.config_id.cash_journal.id:
				vals = {
					'statement_id': statement.id,
					'ref': 'Deposito ' + session.name,
					'name': 'Deposito ' + session.name,
					'amount': self.amount * (-1),
					'date': str(date.today()),
					}
		statement_line = self.env['account.bank.statement.line'].create(vals)		
		vals_deposit = {
			'user_id': self.env.context['uid'],
			'session_id': session.id,
			'date': str(date.today()),
			'amount': self.amount,
			'name': 'Deposito ' + session.name,
			'statement_line_id': statement_line.id,
			}
		deposit_id = self.env['pos.session.deposit'].create(vals_deposit)
		
		vals_move = {
			'date': str(date.today()),
			'journal_id': session.config_id.journal_id.id,
			'ref': 'Deposito ' + session.name,
			}
		move_id = self.env['account.move'].create(vals_move)
		if move_id:
			debit_account_id = session.config_id.bank_account.id
			vals_debit = {
				'account_id': debit_account_id,
				'name': 'Deposito ' + session.name,
				'partner_id': self.user_id.partner_id.id,
				'debit': self.amount,
				'move_id': move_id.id
				}
			debit_line_id = self.env['account.move.line'].create(vals_debit)
			vals_credit = {
				'account_id': credit_account_id,
				'name': 'Deposito ' + session.name,
				'partner_id': self.user_id.partner_id.id,
				'credit': self.amount,
				'move_id': move_id.id
				}
			credit_line_id = self.env['account.move.line'].create(vals_credit)
			move_id.post()
			vals_line = {
				'journal_entry_id': move_id.id,
				}
			statement_line.write(vals_line)
			
			

	name = fields.Char('Nombre')
	user_id = fields.Many2one('res.users')
	session_id = fields.Many2one('pos.session')
	date = fields.Date('Fecha')
	amount = fields.Float('Monto')
	#nro_deposito = fields.Char('Nro. Deposito')


class add_sale_order_cuotas(models.TransientModel):
	_name = 'add.sale.order.cuotas'

	sale_cuotas_id = fields.Many2one('sale.cuotas',required=True)

	@api.multi
	def insert_cuotas(self):
		if not self.sale_cuotas_id:
			raise ValidationError('Por favor, seleccione una cuota')

		order_id = self.env.context['active_id']
		order = self.env['sale.order'].browse(order_id)
		if order:
			for line in order.order_line:
				cuota_id = self.env['sale.cuotas'].search([('product_id','=',line.product_id.id)])
				if cuota_id:
					line.unlink()
			vals_line = {
				'product_id': self.sale_cuotas_id.product_id.id,
				'name': self.sale_cuotas_id.name,
				'price_unit': self.sale_cuotas_id.monto,
				'product_uom_qty': 1,
				'order_id': order_id
				}
			order_line = self.env['sale.order.line'].create(vals_line)
		return None
	
class product_update_prices(models.TransientModel):
	_name = 'product.update.prices'

	categ_id = fields.Many2one('product.category',string='Categoria')
	product_id = fields.Many2one('product.product',string='Producto')
	supplier_id = fields.Many2one('res.partner',string='Proveedor',domain=[('supplier','=',True)])
	list_price_update = fields.Float('Porcentaje Precio Venta',default=0)
	cost_price_update = fields.Float('Porcentaje Precio Costo',default=0)

	@api.multi
	def update_costs(self):
		if not self.categ_id and not self.supplier_id and not self.product_id:
			raise ValidationError("Debe ingresar al menos un parametro de actualizacion")
		if self.list_price_update < 0 or self.list_price_update > 100:
			raise ValidationError("El precio de venta a ingresar solo puede ser aumentando entre un 0% y 100%")
		if self.cost_price_update < 0 or self.cost_price_update > 100:
			raise ValidationError("El costo a ingresar solo puede ser aumentando entre un 0% y 100%")
		domain = []
		if self.categ_id:
			domain.append(('categ_id','=',self.categ_id.id))
		if self.supplier_id:
			domain.append(('supplier_id','=',self.supplier_id.id))
		if self.product_id:
			domain.append(('id','=',self.product_id.id))
		products = self.env['product.product'].search(domain)
		for product in products:
			cost = product.standard_price
			lst_price = product.list_price
			vals = {}
			if self.list_price_update > 0:
				vals['lst_price'] = lst_price * ( 1 + (self.list_price_update/100.00) )
			if self.cost_price_update > 0:
				vals['standard_price'] = cost * ( 1 + (self.cost_price_update/100.00) )
			product.write(vals)
		return None
