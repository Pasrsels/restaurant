from django.shortcuts import render
from django.views.generic import ListView, DetailView, CreateView
from .models import Production
from django.http import JsonResponse, Http404
from django.template.loader import render_to_string
from loguru import logger
from django.db.models import F, Sum, DecimalField
from inventory.models import Dish, Ingredient
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
import json
from .forms import *
from inventory.models import EndOfDay, EndOfDayItems, CheckList
from django.db import transaction
import datetime
from permisions.permisions import can_confirm_required, can_declare_required
from collections import defaultdict
from inventory.models import Logs

class ProductionListView(ListView):
    model = Production
    template_name = "production/production_list.html"
    context_object_name = "productions"
    paginate_by = 20
    ordering = ['-created']

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        queryset = queryset.filter(branch=user.branch).select_related(
            "branch"
        ).annotate(
            planned_cost=Sum(F('productionitem__actual_portions') * F('productionitem__dish__cost'), 
                             output_field=DecimalField(max_digits=10, decimal_places=2)),
            total_planned=Sum(F('productionitem__portions') * F('productionitem__dish__cost'),
                              output_field=DecimalField(max_digits=10, decimal_places=2))
        )
         
        return queryset.select_related("branch")

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            productions_html = render_to_string(
                "production/production_list_rows.html",
                {"productions": context["productions"]},
                request=self.request,
            )
            productions = context.get("productions")
            if hasattr(productions, "has_next"):
                has_next = productions.has_next()
            else:
                page_obj = context.get("page_obj")
                has_next = page_obj.has_next() if page_obj is not None else False

            return JsonResponse({
                "productions_html": productions_html,
                "has_next": has_next,
            })
        else:
            return super().render_to_response(context, **response_kwargs)

    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except Http404:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"productions_html": "", "has_next": False})
            raise

class ProductionDetailView(DetailView):
    model = Production
    template_name = "production/detail.html"
    context_object_name = "production"
    
    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        return queryset.filter(branch=user.branch).select_related("branch")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        production = self.get_object()

        production_items = ProductionItem.objects.filter(
            production=production
        ).select_related('dish')

        dish_ids = production_items.values_list('dish_id', flat=True)
        ingredients = Ingredient.objects.filter(
            dish_id__in=dish_ids
        ).select_related('raw_material')
   
        dish_ingredients = defaultdict(list)
        for ingredient in ingredients:
            dish_ingredients[ingredient.dish_id].append(ingredient)
            
        ingredient_usage = defaultdict(float)
        for item in production_items:
            for ingredient in dish_ingredients.get(item.dish_id, []):
                usage = (ingredient.quantity * item.portions) / item.dish.portion_multiplier
                ingredient_usage[ingredient.raw_material] += usage
        
        context['production_items'] = production_items
        context['production_plan_items'] = ProductionItem.objects.filter(
            production=production
        ).select_related('dish')
        context['ingredient_usage'] = dict(ingredient_usage)
        context['production_ingredients'] = ProductionIngredients.objects.filter(
            production=production
        ).select_related('ingredient')
        context['raw_material_allocations'] = ProductionRawMaterialAllocation.objects.filter(
            production=production
        ).select_related('product')
        
        return context
    
@login_required
@can_confirm_required
def confirm(request):
    try:
        data = json.loads(request.body)
        production_id = int(data.get('production_id'))

        production = Production.objects.get(id=production_id, branch=request.user.branch)
        production.confirm = True
        production.save()

        logger.success(f'Production: {production.plan_number} confirmed')
        return JsonResponse({'success':True, 'message':"Production confirmed"}, status=200)
    
    except Exception as e:
        logger.error(f'Failed to process confirmation: {e}')
        return JsonResponse({'success':False}, status=400)


@login_required
@can_confirm_required
def confirm_production(request, pp_id):
    if request.method == 'GET':
        try:
            production_plan = Production.objects.get(id=pp_id, branch=request.user.branch)
            production_plan_items = ProductionItem.objects.filter(production=production_plan).select_related('dish')
            dish_ingridients = Ingredient.objects.filter(raw_material__branch=request.user.branch)
            total_cost_items = production_plan_items.aggregate(total_cost=Sum('total_cost'))['total_cost'] or 0
        
            raw_materials = []
            
            for item in production_plan_items:
                for ing in Ingredient.objects.filter(dish=item.dish, raw_material__branch=request.user.branch):
                   
                    raw_material_in, _ = ProductionInventory.objects.get_or_create(
                        raw_material=ing.raw_material,
                        branch=request.user.branch,
                        defaults={'quantity': 0}
                    )

                    allocation, _ = ProductionRawMaterialAllocation.objects.get_or_create(
                        product=ing.raw_material,
                        branch = request.user.branch,
                        production=production_plan
                    )

                    required_quantity = ing.quantity * (item.portions / item.dish.portion_multiplier)
                    current_quantity = raw_material_in.quantity if raw_material_in else 0
                    expected_quantity = required_quantity - current_quantity

                    if expected_quantity < 0:
                        expected_quantity = 0

                    logger.info(f'Raw material: {ing.raw_material.name}, Required quantity: {required_quantity}, Current quantity: {current_quantity}, Expected quantity: {expected_quantity}')

                    
                    allocation.expected_quantity=expected_quantity
                    allocation.save()

                    logger.info(f'Raw material: {ing.raw_material.name}, Allocated quantity: {allocation.expected_quantity}')

                    raw_material_found = next((rm for rm in raw_materials if rm['id'] == ing.raw_material.id), None)
                    if raw_material_found:
                        raw_material_found['quantity'] += required_quantity
                        raw_material_found['expected_quantity'] += expected_quantity
                        raw_material_found['quantity_b_f'] += current_quantity
                        raw_material_found['allocated_quantity'] = allocation.quantity if allocation else None
                    else:
                        raw_materials.append(
                            {
                                'id': ing.raw_material.id,
                                'name': ing.raw_material.name,
                                'quantity_b_f': float(current_quantity),
                                'quantity': float(required_quantity),
                                'expected_quantity': allocation.expected_quantity,
                                'dish': item.dish.name,
                                'production_id': pp_id,
                                'allocated_quantity': allocation.quantity if allocation else None
                            }
                        )

            return render(request, 'production/confirm_production.html', 
                {
                    'production': production_plan,
                    'production_plan_items': production_plan_items,
                    'total_cost_items': total_cost_items,
                    'production_plan_minor_items': raw_materials,
                    'dish_ing': dish_ingridients
                }
            )
        except Exception as e:
            logger.error(f'Error in confirm_production: {e}')
            return JsonResponse({'success': False, 'message': f'Error: {e}'}, status=500)


@login_required 
@can_confirm_required
def confirm_production_item(request):
    """
        raw_material allocation for production
    """
    try:
        data = json.loads(request.body)
        raw_material_id = data.get('raw_material_id')
        quantity = data.get('quantity')
        production_id = data.get('production_id')
        quantity = float(quantity)
        
        with transaction.atomic():
            raw_material = Product.objects.select_for_update().get(id=raw_material_id, branch=request.user.branch)
            production = Production.objects.get(id=production_id, branch=request.user.branch)

            main_before = float(raw_material.quantity or 0)
            main_after = max(main_before - float(quantity), 0)
            main_delta = main_after - main_before  
            raw_material.quantity = main_after
            raw_material.save(update_fields=["quantity"])

            p_raw_material, created = ProductionInventory.objects.select_for_update().get_or_create(
                raw_material=raw_material,
                branch=request.user.branch,
                defaults={"quantity": 0},
            )
            kitchen_before = float(p_raw_material.quantity or 0)
            p_raw_material.quantity = kitchen_before + float(quantity)
            p_raw_material.save(update_fields=["quantity"])
            kitchen_after = float(p_raw_material.quantity)
            kitchen_delta = kitchen_after - kitchen_before  

            allocation = ProductionRawMaterialAllocation.objects.get(product=raw_material, production=production)
            allocation.quantity = float(quantity)
            allocation.save(update_fields=["quantity"]) 

            Logs.objects.create(
                user=request.user,
                action='Transfer',
                description=f'to production for production {production.plan_number}',
                product=raw_material,
                quantity=main_delta,  
                total_quantity=main_after,
            )

            ProductionLogs.objects.create(
                user=request.user,
                action='stock in',
                description=f'from stores for production {production.plan_number}',
                product=p_raw_material,
                quantity=kitchen_delta,  
                total_quantity=kitchen_after,
            )

            return JsonResponse({'success': True}, status=200)

    except Exception as e:
        logger.error(f'Failed processing: {e}')
        return JsonResponse({'success': False, 'message': f'{e}'}, status=400)

    
@login_required
@transaction.atomic
def create_production_plan(request):

    if request.method == 'GET':
        form = ProductionPlanInlineForm()
        return render(request, 'production/create_production.html', {'form': form})
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info(data)

            items = data.get('cart', [])

            if not items or not isinstance(items, list):
                return JsonResponse({'success': False, 'message': 'Invalid data: items should be a list'}, status=400)
            
            production_plan = Production.objects.create(
                confirm=False,
                declared=False, 
                branch=request.user.branch,
            )

            dish_names = [item.get('dish') for item in items if item.get('dish')]
            dishes = Dish.objects.filter(name__in=dish_names, branch = request.user.branch).select_related('branch')
            dish_map = {dish.name: dish for dish in dishes}

            if len(dish_map) != len(dish_names):
                return JsonResponse({'success': False, 'message': 'Some dishes do not exist'}, status=404)

            production_items = []
            production_items_update = []
            raw_materials_to_checklist = set()

            for item in items:
                portions = item.get('portions')
                dish_name = item.get('dish')
                total_cost = item.get('total_cost')

                if not portions or not dish_name:
                    return JsonResponse({'success': False, 'message': 'Missing data: portions or dish'}, status=400)

                dish = dish_map.get(dish_name)

                if dish is None:
                    return JsonResponse({'success': False, 'message': f'Dish {dish_name} does not exist'}, status=404)

                ingredients = Ingredient.objects.filter(dish=dish, raw_material__branch = request.user.branch).select_related('raw_material', 'dish')
                
                production_items.append(ProductionItem(
                    production=production_plan,
                    portions=portions,
                    dish=dish,
                    total_cost=total_cost
                ))

                for ingredient in ingredients:
                    raw_materials_to_checklist.add(ingredient.raw_material)

            if production_items:
                ProductionItem.objects.bulk_create(production_items)

            if production_items_update:
                ProductionItem.objects.bulk_update(production_items_update, ['portions', 'total_cost', 'allocated'])
                
            #create e_o_d
            e_o_d, created = EndOfDay.objects.get_or_create(date=datetime.datetime.today(), branch=request.user.branch, done=False)
            
            if created:
                
                logger.info(f'End of day created: {e_o_d}')
                
                for dish in production_items:
                    EndOfDayItems.objects.create(
                        end_of_day=e_o_d,
                        dish_name=dish.dish.name,
                        total_portions=dish.portions,
                        total_sold=0,
                        staff_portions=0
                    )
            else:
                existing_items = EndOfDayItems.objects.filter(end_of_day=e_o_d).values_list('dish_name', flat=True)
                
                logger.info(f'Existing End of day')
                
                for dish in production_items:
                    if dish.dish.name not in existing_items:
                        EndOfDayItems.objects.create(
                        end_of_day=e_o_d,
                        dish_name=dish.dish.name,
                        total_portions=dish.portions,
                        total_sold=0,
                        staff_portions=0
                    )
                        
                    logger.success(f'Added new dish to End of Day: {dish.dish.name}')

            return JsonResponse(
                {
                    'success': True, 
                    'message': 'Production plan created successfully', 
                    'p_plan_id': production_plan.id
                }, 
                status=201
            )
        except Exception as e:
            logger.error(f"Error in create_production_plan: {e}")
            return JsonResponse({'success': False, 'message': f'Error: {e}'}, status=500)

    return JsonResponse({'success': False, 'message': 'Invalid HTTP method'}, status=405)

@login_required
# @can_declare_required
def confirm_declaration(request, production_id):
    try:
        production = Production.objects.get(id=production_id, branch=request.user.branch)

        if production.confirm:

            production.declared=True
            production.save()

            return JsonResponse({'message':'Production successfully Declared', 'success':True}, status=200)
        return JsonResponse({'success':False, 'message':'Confirm Production First!'}, status=400)
        
    except Exception as e:
        logger.error(f'Failed to declare production plan {production}', status=400)
        return JsonResponse({'success':False, 'message':"{e}"})

@login_required
@can_declare_required
def declare_production(request, plan_id):
    try:
        production_plan = Production.objects.get(id=plan_id, branch=request.user.branch)
        production_plan_items = ProductionItem.objects.filter(production=production_plan).select_related('dish')
        dish_ingridients = Ingredient.objects.filter(raw_material__branch=request.user.branch)
        total_cost_items = production_plan_items.aggregate(total_cost=Sum('total_cost'))['total_cost'] or 0
    
        raw_materials = []
        
        for item in production_plan_items:
            for ing in Ingredient.objects.filter(dish=item.dish, raw_material__branch=request.user.branch):
                
                raw_material_in, _ = ProductionInventory.objects.get_or_create(
                    raw_material=ing.raw_material,
                    branch=request.user.branch,
                    defaults={'quantity': 0}
                )

                allocation, _ = ProductionRawMaterialAllocation.objects.get_or_create(
                    product=ing.raw_material,
                    branch = request.user.branch,
                    production=production_plan
                )

                required_quantity = ing.quantity * (item.portions / item.dish.portion_multiplier)
                current_quantity = raw_material_in.quantity if raw_material_in else 0
                expected_quantity = required_quantity - current_quantity

                
                allocation.expected_quantity=expected_quantity
                allocation.save()

                raw_material_found = next((rm for rm in raw_materials if rm['id'] == ing.raw_material.id), None)
                if raw_material_found:
                    raw_material_found['quantity'] += required_quantity
                    raw_material_found['expected_quantity'] += expected_quantity
                    raw_material_found['quantity_b_f'] += current_quantity
                    raw_material_found['allocated_quantity'] = allocation.quantity if allocation else None
                else:
                    raw_materials.append(
                        {
                            'id': ing.raw_material.id,
                            'name': ing.raw_material.name,
                            'quantity_b_f': float(current_quantity),
                            'quantity': float(required_quantity),
                            'expected_quantity': allocation.expected_quantity,
                            'dish': item.dish.name,
                            'production_id': plan_id,
                            'allocated_quantity': allocation.quantity if allocation else None
                        }
                    )

        for raw_material in raw_materials:
            p_ing, _ = ProductionIngredients.objects.get_or_create(
                production=production_plan,
                ingredient_id=raw_material['id'],
                defaults={
                    'quantity':raw_material['quantity'],
                }
            )

            p_ing.quantity = raw_material['quantity']
            p_ing.save()

        logger.info(f'production ingredients: {raw_materials}')

        return render(request, 'production/declare_production.html', 
            {
                'production': production_plan,
                'production_plan_items': production_plan_items,
                'total_cost_items': total_cost_items,
                'production_plan_minor_items': raw_materials,
                'dish_ing': dish_ingridients
            }
        )
    except Exception as e:
        logger.error(f'Error in declare production: {e}')
        return JsonResponse({'success': False, 'message': f'Error: {e}'}, status=500)
    
@login_required
@can_declare_required
def process_dish_declaration(request, plan_id):
    """
    Process declared portions for dishes and recalculate raw material requirements
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)
    
    try:
        data = json.loads(request.body)
        dish_id = data.get('dish_id')
        declared_portions = float(data.get('declared_portions', 0))
        
        if not dish_id or declared_portions <= 0:
            return JsonResponse({
                'success': False, 
                'message': 'Invalid dish or portions'
            }, status=400)
        
        with transaction.atomic():

            production_plan = Production.objects.get(id=plan_id, branch=request.user.branch)
            production_item = ProductionItem.objects.get(
                production=production_plan,
                dish_id=dish_id
            )
            
            planned_portions = production_item.portions
            portion_variance = declared_portions - planned_portions
            
            production_item.declared_portions = declared_portions
            production_item.variance = portion_variance
            production_item.save()
            
            updated_raw_materials = []
            ingredients_qs = Ingredient.objects.filter(
                dish=production_item.dish,
                raw_material__branch=request.user.branch
            ).select_related('raw_material')

            for ing in ingredients_qs:
                required_quantity = float(ing.quantity) * (declared_portions / production_item.dish.portion_multiplier)

                p_inv, _ = ProductionInventory.objects.get_or_create(
                    raw_material=ing.raw_material,
                    branch=request.user.branch,
                    defaults={'quantity': 0}
                )

                before_qty = float(p_inv.quantity or 0)
                after_qty = max(before_qty - required_quantity, 0)
                p_inv.quantity = after_qty
                p_inv.save()

                ProductionLogs.objects.create(
                    user=request.user,
                    action='declared',
                    description=f'declared quantity for production {production_plan.plan_number}',
                    product=p_inv,
                    quantity=-required_quantity,
                    total_quantity=after_qty,
                )

                allocation = ProductionRawMaterialAllocation.objects.filter(
                    product=ing.raw_material,
                    branch=request.user.branch,
                    production=production_plan,
                ).first()

                p_ing, _ = ProductionIngredients.objects.update_or_create(
                    production=production_plan,
                    ingredient_id=ing.raw_material.id,
                ) 

                if p_ing.declared_quantity:
                    p_ing.declared_quantity += float(declared_portions / production_item.dish.portion_multiplier)
                else:
                    p_ing.declared_quantity = 0
                    p_ing.declared_quantity += float(declared_portions / production_item.dish.portion_multiplier)
                
                p_ing.variance = p_ing.quantity - p_ing.declared_quantity
                p_ing.save()

                updated_raw_materials.append({
                    'id': ing.raw_material.id,
                    'name': ing.raw_material.name,
                    'quantity': float(required_quantity),
                    'expected_quantity': 0.0,
                    'quantity_b_f': before_qty,
                    'allocated_quantity': allocation.quantity if allocation and allocation.quantity else 0,
                })
            
            return JsonResponse({
                'success': True,
                'message': 'Dish declaration processed successfully',
                'portion_variance': float(portion_variance),
                'declared_portions': float(declared_portions),
                'planned_portions': float(planned_portions),
                'raw_materials': updated_raw_materials
            })
            
    except Production.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Production plan not found'
        }, status=404)
    except ProductionItem.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Production item not found'
        }, status=404)
    except Exception as e:
        logger.error(f'Error processing dish declaration: {e}')
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)
    
@login_required
def get_raw_materials(request, production_id):
    try:
        production_plan = Production.objects.get(id=production_id, branch=request.user.branch)
        raw_materials = ProductionIngredients.objects.filter(production=production_plan)
        data = [{
            'id': rm.ingredient.id,
            'cost': float(rm.ingredient.cost),
            'name': rm.ingredient.name,
            'remaining_quantity':float(rm.remaining_quantity) if rm.remaining_quantity else 0,
            'actual_quantity': float(rm.actual_quantity) if rm.actual_quantity else 0,
            'quantity': float(rm.quantity) if rm.quantity else 0,
            'declared_quantity':float(rm.declared_quantity) if rm.declared_quantity else 0,
            'expected_quantity': float(getattr(rm, 'expected_quantity', 0)),
            'allocated_quantity': float(getattr(rm, 'allocated_quantity', 0)),
        } for rm in raw_materials]

        return JsonResponse({'success': True, 'raw_materials': data}, status=200)
    except Exception as e:
        logger.debug(f'Error getting raw materials: {e}')
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
def process_remaining_kgs(request, production_id):
    try:
        data = json.loads(request.body)
        remaining_kgs = float(data.get('remaining_kgs'))
        raw_material_id = data.get('raw_material_id')

        production_plan = Production.objects.get(id=production_id, branch=request.user.branch)
        raw_material = ProductionIngredients.objects.filter(production=production_plan, ingredient__id=raw_material_id).first()

        raw_material.remaining_quantity = remaining_kgs
        raw_material.actual_quantity = raw_material.declared_quantity - remaining_kgs
        raw_material.variance = raw_material.declared_quantity - raw_material.actual_quantity
        raw_material.save()

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@method_decorator([login_required], name='dispatch')
class DishListView(ListView):
    model = Dish
    template_name = "production/dish/dish_list.html"
    context_object_name = "dishes"
    paginate_by = 20
    ordering = ['-created']

    def get_queryset(self):
        dishes = Dish.objects.filter(branch=self.request.user.branch).select_related('branch')
        return dishes
    
    def get_context_data(self, **kwargs):
        """
            Add ingredients data to the context.
        """
        context = super().get_context_data(**kwargs)
        branch = self.request.user.branch
        
        ingredients_qs = Ingredient.objects.filter(dish__branch=branch).select_related('raw_material', 'dish')

        ingredients_by_dish = defaultdict(list)
        for ingredient in ingredients_qs:
            ingredients_by_dish[ingredient.dish_id].append(ingredient)

        context['ingredients_by_dish'] = ingredients_by_dish
        return context
    
    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            dishes_html = render_to_string(
                "production/dish/dish_list_rows.html",
                {"dishes": context["dishes"], "ingredients": context["ingredients"]},
                request=self.request,
            )
            dishes = context.get("dishes")
            if hasattr(dishes, "has_next"):
                has_next = dishes.has_next()
            else:
                page_obj = context.get("page_obj")
                has_next = page_obj.has_next() if page_obj is not None else False

            return JsonResponse({
                "productions_html": dishes_html,
                "has_next": has_next,
            })
        else:
            return super().render_to_response(context, **response_kwargs)
    
@login_required
def create_dish(request):
    form = IngredientForm()
    dish_form = DishForm()
    
    if request.method == 'GET':
        products = Product.objects.filter(branch=request.user.branch).select_related('branch')
        r_m = products.filter(raw_material=True)
        packaging_products = products.filter(packaging=True)

        context = {
            'r_m': r_m,
            'form': form,
            'dish_form': dish_form,
            'packaging_products':packaging_products
        }
        return render(request, 'production/dish/create_dish.html', context)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info(data)
            dish_info = data.get('dish_info')
            ingredients = data.get('ingredients', [])
        
            dish_name = dish_info.get('name').strip()
            portion_multiplier = dish_info.get('portion_multiplier')
            cost = dish_info.get('dish_cost', 0)
            selling_price = dish_info.get('selling_price')
            category = dish_info.get('category')
            supplies = dish_info.get('supplies', [])

            logger.info(f"Received data for new dish: {dish_name}, Portion Multiplier: {portion_multiplier}, Cost: {cost}, Selling Price: {selling_price}, Category: {category}, Supplies: {supplies}")

            if not dish_name or not portion_multiplier or not selling_price:
                return JsonResponse({'success': False, 'message': f'Please fill all the missing data'}, status=400)
            
            with transaction.atomic():
                dish = Dish.objects.create(
                    cost = cost,
                    name = dish_name,
                    portion_multiplier = portion_multiplier,
                    price = selling_price,
                    category=category,
                    branch=request.user.branch
                )
                
                for item in ingredients:
                    raw_material = Product.objects.get(name=item.get('raw_material'), branch=request.user.branch)
                    Ingredient.objects.create(
                        dish=dish,
                        note=item.get('note'),
                        raw_material=raw_material,
                        quantity=item.get('quantity'),
                    )

                supplies_objs = []
                for supply in supplies:
                    supply_product = Product.objects.get(name=supply.get('supply_name'), branch=request.user.branch)
                    supplies_objs.append(Supplies(
                        dish=dish,
                        type='dish',
                        item=supply_product,
                        quantity=supply.get('quantity')
                    ))
                if supplies_objs:
                    Dish.objects.bulk_create(supplies_objs)

                logger.success(f'Dish created: {dish.name} with ID {dish.id}')
            
                return JsonResponse({
                    'success': True, 
                    'message': f'Dish {dish.name} created successfully!',
                    'dish_id': dish.id
                }, status=201)
                
        except Exception as e:
            logger.error(f"Error creating dish: {e}")
            return JsonResponse({'success': False, 'message': f'{e}'}, status=400)

@login_required
def edit_dish(request, dish_id):
    if request.method == 'GET':
        try:
            dish = Dish.objects.get(id=dish_id, branch=request.user.branch)
            dish_form = DishForm()
            r_m = Product.objects.filter(raw_material=True, branch=request.user.branch)

            return render(request, 'inventory/edit_dish.html',{
                'r_m':r_m,
                'dish':dish,
                'dish_form': dish_form
            })
        except Exception as e:
            logger.error(f'Error fetching dish: {e}')
            return JsonResponse({'success':False, 'message':f'Dish not found'}, status=404)
        
    if request.method == 'POST':
        try:
            dish_name = request.POST.get('name')
            cost = request.POST.get('dish_cost')
            selling_price = request.POST.get('selling_price')
            portion_multiplier = request.POST.get('portion_multiplier')
            category = request.POST.get('category')
            image = request.FILES.get('image')
            cart = json.loads(request.POST.get('cart'))

            cat, _= MealCategory.objects.get_or_create(name=category) 
            dish = Dish.objects.get(id=dish_id)


            dish.name = dish_name
            dish.portion_multiplier = portion_multiplier
            dish.cost = cost
            dish.price = selling_price
            dish.category = dish.category

            existing_ingredients = Ingredient.objects.filter(dish=dish, raw_material__branch = request.user.branch).select_related('raw_material')
            existing_ingredient_names = {ing.raw_material.name for ing in existing_ingredients}
            raw_material_map = {rm.name: rm for rm in Product.objects.filter(branch = request.user.branch)}

            ingredient_updates = []
            ingredients_to_delete = existing_ingredients[:]

            for item in cart:
                raw_material_name = item['raw_material']
                raw_material = raw_material_map.get(raw_material_name)

                if not raw_material:
                    return JsonResponse({'success': False, 'message': f'Raw material "{raw_material_name}" not found.'})

                if raw_material_name in existing_ingredient_names:
                    ing = next(ing for ing in existing_ingredients if ing.raw_material.name == raw_material_name)
                    ing.quantity = item['quantity']
                    ing.note = item['note']
                    ingredient_updates.append(ing)

                    ingredients_to_delete.remove(ing)
                else:
                    ingr = Ingredient.objects.create(
                        dish=dish,
                        raw_material=raw_material,
                        quantity=item['quantity'],
                        note=item['note'],
                    )
                    logger.info(f'Added new ingredient: {ingr}')

            if ingredients_to_delete:
                logger.info(f'Deleting ingredients: {ingredients_to_delete}')
                Ingredient.objects.filter(id__in=[ing.id for ing in ingredients_to_delete], raw_material__branch = request.user.branch).delete()

            if ingredient_updates:
                logger.info(f'Updating ingredients: {ingredient_updates}')
                with transaction.atomic():
                    Ingredient.objects.bulk_update(ingredient_updates, fields=['quantity', 'note'])

            dish.save()
            return JsonResponse({'success': True}, status=200)

        except Exception as e:
            logger.error(f'Error processing request: {e}')
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success':False, 'message':'Invalid request'}, status=500)
        
@login_required
def dish_json_detail(request):
    try:
        ingredients = []
        data = json.loads(request.body)
        dish_id = int(data.get("dish_id"))
        
        if not dish_id or dish_id == '':
            return JsonResponse({'success': False, 'message': 'Dish ID is required and cannot be empty'}, status=400)
        
        dish = Dish.objects.get(id=dish_id, branch=request.user.branch)
        
        for ingredient in Ingredient.objects.filter(dish=dish, raw_material__branch=request.user.branch):
            if dish == ingredient.dish:
                ingredients.append(
                {
                    'name' : f'{ingredient.raw_material}',
                    'quantity':ingredient.quantity,
                    'cost': ingredient.raw_material.cost,
                    'selling': ingredient.dish.price
                }
            )
        
        return JsonResponse({
            'success': True,
            'data': ingredients,
            'portion_multiplier': dish.portion_multiplier
        })
    except Exception as e:
        logger.error(f"Error in dish_json_detail: {e}")
        return JsonResponse({'success': False, 'message': f'{e}'}, status=400)

@login_required
def production_inventory(request):
    products = ProductionInventory.objects.filter(branch=request.user.branch).select_related('raw_material', 'branch')
    logger.info(f'Production Inventory: {products}')
    return render(request, 'production/production_inventory.html', {'products': products})
