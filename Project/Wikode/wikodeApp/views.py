from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from wikodeApp.models import Author, Keyword, RegistrationApplication, Article, Tag, TagRelation
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from wikodeApp.forms import ApplicationRegistrationForm, GetArticleForm, TagForm, FilterForm
from wikodeApp.utils.activityManager import ActivityManager
from wikodeApp.utils.fetchArticles import createArticles
import string
import random
from wikodeApp.utils.textSearch import Search
from dal import autocomplete
from wikodeApp.utils.wikiManager import getLabelSuggestion, WikiEntry


@login_required
def homePage(request):
    if request.method == 'POST':
        search_terms = request.POST.get('searchTerms').split(",")
        search = Search(search_terms)

        filter_form = FilterForm(request.POST)
        if filter_form.is_valid():
            search.filterArticles(filter_form.cleaned_data)
        results_list = search.getSearchResults(filter_form.cleaned_data.get('order_by'))

        page = request.POST.get('page', 1)
        paginator = Paginator(results_list, 25)
        search_str = request.POST.get('searchTerms')
        filter_params = filter_form.cleaned_data
        filter_params_str = '&'.join([filter_key + '=' + str(filter_params.get(filter_key))
                                     for filter_key in filter_params
                                     if filter_params.get(filter_key)]
                                    )
        try:
            results = paginator.page(page)
        except PageNotAnInteger:
            results = paginator.page(1)
        except EmptyPage:
            results = paginator.page(paginator.num_pages)

        if results_list:
            date_data = search.getYearlyArticleCounts()
        else:
            date_data = {}
        context = {"results_list": results,
                   "search_term": search_str,
                   "filter_params": filter_params_str,
                   "date_labels": date_data.keys(),
                   "data_values": date_data.values(),
                   "parent_template": "wikodeApp/searchResults.html",
                   "filter_form": filter_form,
                   "result_size": len(results_list)
                   }
    else:
        # todo: Look for a pagination without rerunning search query
        if request.GET.get('page', False):
            page = request.GET.get('page')
            search_terms = request.GET.get('term').split(",")

            search = Search(search_terms)
            filter_params = {
                "start_date": request.GET.get('start_date', None),
                "end_date": request.GET.get('end_date', None),
                "author_field": request.GET.get('author_field', None),
                "journal_field": request.GET.get(('journal_field', None)),
                "keywords_field": request.GET.get('keywords_field', None),
                "order_by": request.GET.get('order_by', None)
            }

            search.filterArticles(filter_params)
            results_list = search.getSearchResults(filter_params.get('order_by'))

            paginator = Paginator(results_list, 25)
            search_str = request.GET.get('term')

            filter_params_str = '&'.join([filter_key + '=' + str(filter_params.get(filter_key))
                                          for filter_key in filter_params
                                          if filter_params.get(filter_key)]
                                         )
            try:
                results = paginator.page(page)
            except PageNotAnInteger:
                results = paginator.page(1)
            except EmptyPage:
                results = paginator.page(paginator.num_pages)

            context = {"results_list": results,
                       "search_term": search_str,
                       "filter_params": filter_params_str,
                       "parent_template": "wikodeApp/searchResults.html",
                       "filter_form": FilterForm(initial=filter_params),
                       "result_size": len(results_list)
                       }

        else:
            context = {"parent_template": "wikodeApp/homePage.html",
                       "filter_form": FilterForm(initial={'order_by': 'relevance'})}

    return render(request, 'wikodeApp/searchAndFilterBox.html', context=context)


@login_required
def articleDetail(request, pk):
    article = Article.objects.get(pk=pk)
    wiki_info = {}
    if request.method == 'GET':
        activity_manager = ActivityManager(user_id=request.user.id)
        activity_manager.saveViewActivity('3', article.id)
    # Begin: Get Tag
    if request.method == 'POST':
        print(request.POST)
        if 'get_tag' in request.POST:
            tag_form = TagForm(data=request.POST)
            tag_data = WikiEntry(tag_form.data['wikiLabel'])
            wiki_info['qid'] = tag_data.getID()
            wiki_info['label'] = tag_data.getLabel()
            wiki_info['description'] = tag_data.getDescription()

        elif 'add_tag' in request.POST:
            tag_data = WikiEntry(request.POST['qid'])
            fragment_text = request.POST['fragment_text']
            fragment_start_index = request.POST['fragment_start_index']
            fragment_end_index = request.POST['fragment_end_index']
            tag = tag_data.saveTag()
            tag_data.saveRelatedWikiItems()

            TagRelation.objects.get_or_create(article=article,
                                              tag=tag,
                                              fragment=fragment_text,
                                              start_index=fragment_start_index,
                                              end_index=fragment_end_index
                                              )

        elif 'tag_relation_id' in request.POST:
            tag = TagRelation.objects.get(id=request.POST['tag_relation_id'])
            tag.delete()

    tag_form = TagForm()
    authors = Author.objects.filter(article=article)
    keywords = Keyword.objects.filter(article=article)
    keywords_list = ', '.join([item.KeywordText for item in keywords])
    tags = TagRelation.objects.filter(article=article).select_related('tag')

    article_dict = {"authors": authors,
                    "title": article.Title,
                    "abstract": article.Abstract,
                    "pmid": article.PMID,
                    "tag_form": tag_form,
                    "keywords": keywords_list,
                    "tags": tags
                    }

    article_dict.update(wiki_info)

    return render(request, 'wikodeApp/articleDetail.html', context=article_dict)


class TagAutocomplete(autocomplete.Select2ListView):

    def get_list(self):
        taglist = getLabelSuggestion(self.q)
        return taglist


def registration(request):
    if request.method == 'POST':
        registration_form = ApplicationRegistrationForm(data=request.POST)
        if registration_form.is_valid():
            if RegistrationApplication.objects.filter(email=request.POST['email']).filter(
                    applicationStatus='1').exists():
                return render(request, 'wikodeApp/registration.html', {'form': registration_form,
                                                                       'under_review': 'An application with this email is currrently under review. Please try again with another email.',
                                                                       'registration_form': registration_form})
            elif User.objects.filter(email=request.POST['email']).filter(is_active='True').exists():
                return render(request, 'wikodeApp/registration.html', {'form': UserCreationForm(),
                                                                       'same_email': 'This email is used before. Please use another email.',
                                                                       'registration_form': registration_form})
            else:
                registration_form.save()
                return render(request, 'wikodeApp/login.html', {'form': UserCreationForm(),
                                                                'success': 'Thank you for your application. Your account will be activated after reviewed carefully.'})
        else:
            return render(request, 'wikodeApp/registration.html', {'registration_form': registration_form})
    else:
        registration_form = ApplicationRegistrationForm()

    return render(request, 'wikodeApp/registration.html', {'registration_form': registration_form})


@login_required
def registrationRequests(request):
    if request.method == 'POST':
        approved_request = RegistrationApplication.objects.get(pk=request.POST['request_id'])
        approved_request.applicationStatus = '2'
        approved_request.save()
        random_password = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        user = User(username=approved_request.email,
                    first_name=approved_request.name,
                    last_name=approved_request.surname,
                    email=approved_request.email,
                    password=random_password)
        user.set_password(user.password)
        user.save()

        requests_list = RegistrationApplication.objects.filter(applicationStatus='1').order_by('applicationDate')
        requests_dict = {"registration_requests": requests_list, "password": random_password}
        return render(request, 'wikodeApp/registrationRequests.html', context=requests_dict)

    requests_list = RegistrationApplication.objects.filter(applicationStatus='1').order_by('applicationDate')
    requests_dict = {"registration_requests": requests_list}
    return render(request, 'wikodeApp/registrationRequests.html', context=requests_dict)


def userLogin(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(username=username, password=password)

        if user:
            if user.is_active:
                login(request, user)
                return HttpResponseRedirect(reverse('wikodeApp:homePage'))
            else:
                return HttpResponse("Your account is not active.")
        else:
            return render(request, 'wikodeApp/login.html',
                          {'form': AuthenticationForm(), 'error': 'Username or password did not match.'})

    else:
        return render(request, 'wikodeApp/login.html', {})


@login_required
def userList(request):
    if request.method == 'POST':
        if 'user_id' in request.POST:
            removed_user = User.objects.get(pk=request.POST['user_id'])
            removed_user.is_active = False
            removed_user.save()
        elif 'admin_status' in request.POST:
            admin_user = User.objects.get(pk=request.POST['admin_status'])
            admin_user.is_superuser = not admin_user.is_superuser
            admin_user.save()

    users = User.objects.filter(is_active=True)
    cur_username = request.user.username
    admin_status = User.objects.filter(username=cur_username).values_list('is_superuser')
    return render(request, 'wikodeApp/userList.html', {'user_list': users, 'admin': admin_status[0][0]})


@login_required
def userLogout(request):
    logout(request)
    return HttpResponseRedirect(reverse('wikodeApp:userLogin'))


@login_required
def getArticles(request):
    if request.method == 'POST':
        form = GetArticleForm(request.POST)

        if form.is_valid():
            createArticles(form.cleaned_data['article_topic'], form.cleaned_data['volume'])
            saved_count = Article.objects.all().count()
            return render(request, 'wikodeApp/articlesSaved.html', {'saved_count': saved_count})
    else:
        form = GetArticleForm()

    return render(request, 'wikodeApp/fetchArticles.html', {'form': form})


## Renders the profilePage.html with the authenticated user's information
## Navigation item 'Profile'sent opens /myprofile url.
@login_required
def myProfilePage(request):
    user = request.user

    context = {
        'user': user,
    }

    return render(request, 'wikodeApp/profilePage.html', context)


## Renders the profilePage.html with the clicked user's id information as pk
## Navigates to /profile/# url.
@login_required
def getProfilePageOfOtherfUser(request, pk):
    ## TODO
    ## pk arguement may be a unique random 6 digit number that represents the requested user.
    ## Here we need to convert the unique random number to user id. Or have another number that represents user.
    ## For development purpose, pk is hardcoded below.
    other_user = User.objects.get(id=pk)
    session_user = User.objects.get(id=request.user.id)

    if other_user == session_user:
        return redirect('wikodeApp:myProfilePage')

    context = {
        'profile': other_user,
    }

    return render(request, 'wikodeApp/profilePage.html', context)
