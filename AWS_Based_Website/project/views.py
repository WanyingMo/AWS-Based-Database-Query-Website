import traceback

from django.shortcuts import render
# from django.http import HttpResponse
from django.http import JsonResponse
# import mysql.connector as mysql
import time
from django.db import connections
import re
from project import mongoClient
from datetime import datetime
import sqlparse
from project.sql2MongoShell import sql2MongoShell

# def index(request):
#     return HttpResponse('project index page')


# connect to mysql by default when the project index page is requested for the first time
def index(request):
    """
    :param request: http request
    :return: index web page with data
    """
    return render(request, 'index.html')


def connectToDB(request):
    """
    :param request: http request
    :return: schema/database name
    """
    databaseType = request.POST.get('databaseType')
    responseStatus = 0  # 0 for no error, 1 for error
    cursor = None
    db = None
    try:
        if databaseType == "mongodb":
            db = mongoClient["instacart"]
        else:
            cursor = connections[databaseType].cursor()
    except Exception as e:
        responseStatus = 1
        traceback.print_exc()
        return JsonResponse({'responseStatus': responseStatus, 'errorDetails': str(e)})
    result = ''
    try:
        if databaseType == 'mysql':
            cursor.execute('select database()')
            result = cursor.fetchone()[0]
        elif databaseType == 'redshift':
            cursor.execute('select current_database()')
            result = cursor.fetchone()[0]
        elif databaseType == 'mongodb':
            result = db.name

    except Exception as e:
        responseStatus = 1
        traceback.print_exc()
        return JsonResponse({'responseStatus': responseStatus, 'errorDetails': str(e)})

    return JsonResponse({'currentDatabase': result})


def checkQuery(query, row, rowPerPage):
    isSelect = False
    # since show, describe doesn't support limit, then only when using select command will we append limit and offset
    if str(query[:6]).lower() == 'select':
        isSelect = True
        # In redshift (postgreSQL), top and limit is not allowed to use together.
        query = query.replace(';', '')
        top = re.search('\s+top\s+(\d+)', query, flags=re.IGNORECASE)
        limitOffset = re.search('\s+limit\s+(\d+)\s*,\s+(\d+)', query, flags=re.IGNORECASE)
        limit = re.search('\s+limit\s+(\d+)', query, flags=re.IGNORECASE)
        offset = re.search('\s+offset\s+(\d+)', query, flags=re.IGNORECASE)
        if top:
            limitNum = int(top.group(1))
            query = re.sub('(\s+top\s+\d+)', '', query, flags=re.IGNORECASE)
            if offset:
                query = re.sub('(\s+offset\s+\d+)', '', query, flags=re.IGNORECASE)
                offsetNum = int(offset.group(1))
            if rowPerPage + row > limitNum:
                query += " limit %s offset %s" % (limitNum - row, row if not offset else row + offsetNum)
            else:
                query += " limit %s offset %s" % (rowPerPage, row if not offset else row + offsetNum)
        elif limitOffset:
            offsetNum = int(limitOffset.group(1))
            limitNum = int(limitOffset.group(2))
            query = re.sub('(\s+limit\s+\d+\s*,\s+\d+)', '', query, flags=re.IGNORECASE)
            if rowPerPage + row > limitNum:
                query += " limit %s offset %s" % (limitNum - row, row + offsetNum)
            else:
                query += " limit %s offset %s" % (rowPerPage, row + offsetNum)
        elif limit:
            limitNum = int(limit.group(1))
            query = re.sub('(\s+limit\s+\d+)', '', query, flags=re.IGNORECASE)
            if offset:
                query = re.sub('(\s+offset\s+\d+)', '', query, flags=re.IGNORECASE)
                offsetNum = int(offset.group(1))
            if rowPerPage + row > limitNum:
                query += " limit %s offset %s" % (limitNum - row, row if not offset else row + offsetNum)
            else:
                query += " limit %s offset %s" % (rowPerPage, row if not offset else row + offsetNum)
        elif offset:
            query = re.sub('(\s+offset\s+\d+)', '', query, flags=re.IGNORECASE)
            offsetNum = int(offset.group(1))
            row += offsetNum
            query += " limit %s offset %s" % (rowPerPage, row)
        else:
            query += " limit %s offset %s" % (rowPerPage, row)
    return query, isSelect


def updateData(request):
    databaseType = request.POST.get('databaseType')         # mysql/redshift/mongoDB
    currentDatabase = request.POST.get('currentDatabase')   # used database/schema
    draw = request.POST.get('draw')                         # number of call
    row = int(request.POST.get('start'))                    # number of records before this page
    rowPerPage = int(request.POST.get('length'))            # number of records displayed in a page
    attribute = request.POST.getlist('attribute[]')         # attribute list of a table
    resultIndex = int(request.POST.get('resultIndex'))      # index of the table in a query result
    query = request.POST.get('query')                       # executed query for the table
    totalRecords = request.POST.get('totalRecords')         # numeric value of number of rows of a table
    print(f"row: {row}")
    print(f"rowPerPage: {rowPerPage}")

    try:
        query, isSelect = checkQuery(query, row, rowPerPage)
    except Exception as e:
        responseStatus = 1
        traceback.print_exc()
        return JsonResponse({'responseStatus': responseStatus, 'errorDetails': str(e)})

    print(f"Executed Query: {query}")

    cursor = None
    mongoCursor = None
    mongoListCursor = None
    try:

        if databaseType == 'mongodb':
            db = mongoClient[currentDatabase]
            if query.lower() == 'show dbs':
                mongoListCursor = []
                for name in mongoClient.list_database_names():
                    mongoListCursor.append({'database': name})
            else:
                mongoQuery = sql2MongoShell(query)
                mongoCursor = eval(mongoQuery)
                mongoListCursor = list(mongoCursor)
        else:
            cursor = connections[databaseType].cursor()
            recordsFiltered = cursor.execute(query)

        if databaseType == 'mysql':
            for i in range(resultIndex):
                cursor.nextset()

        data = []

        if databaseType == 'mongodb':
            for row in mongoListCursor:
                newRow = {}
                for k, v in row.items():
                    newRow["\'" + k + "\'"] = str(v)
                data.append(newRow)
        else:
            if isSelect:
                result = cursor.fetchall()
            else:
                for i in range(row//rowPerPage):
                    cursor.fetchmany(size=rowPerPage)
                result = cursor.fetchmany(size=rowPerPage)

            for row in result:
                data.append({"\'" + attribute[i] + "\'": str(row[i]) for i in range(len(attribute))})
    except Exception as e:
        responseStatus = 1
        traceback.print_exc()
        return JsonResponse({'responseStatus': responseStatus, 'errorDetails': str(e)})

    print(f"draw: {draw}")
    print(f"recordsTotal: {totalRecords}")
    print(f"recordsFiltered: {totalRecords}")
    print(f"data: {data}")

    return JsonResponse({
        'draw': draw,
        'recordsTotal': totalRecords,
        'recordsFiltered': totalRecords,
        'data': data})


# receive ajax request and return requested data
def ajax(request):
    """
    :param request: http request
    :return: json response including query result
    """
    # received data
    databaseType = request.POST.get('databaseType')  # mysql/redshift/mongoDB
    currentDatabase = request.POST.get('currentDatabase')  # used database/schema
    query = str(request.POST.get('query'))  # input sql query
    query = sqlparse.format(query, reindent=True, keyword_case='upper')
    query = sqlparse.split(query)

    # query = [sql.replace('\n', ' ').strip() for sql in query.split(';') if sql]
    print('Received Query: ', query)

    # send data
    tableQuery = query          # query that generates each table
    displayedQuery = []         # query that will be displayed in result section
    resultAttribute = []        # table attribute
    queryResult = []            # table data
    totalRecords = []           # numeric value of number of rows influenced by a sql query
    executedTimeStamp = []      # string value of timestamp when each query is executed
    influencedRowResult = []    # string value of number of rows influenced by a sql query
    executionTime = []          # string value of execution time of each query
    totalExecutionTime = 0      # total time of executing all sql queries
    # currentDatabase           # return the current database/schema back in case it changed

    cursor = None
    db = None
    try:
        if databaseType == 'mongodb':
            db = mongoClient[currentDatabase]
        else:
            cursor = connections[databaseType].cursor()
    except Exception as e:
        responseStatus = 1
        traceback.print_exc()
        return JsonResponse({'responseStatus': responseStatus, 'errorDetails': str(e)})

    for sql in query:

        influencedRow = []
        cursorDescription = []

        mongoCursor = None
        mongoListCursor = None

        startTime = time.time()
        try:
            if databaseType == 'mongodb':
                print(sql)
                if sql.lower() == 'show dbs':
                    # print(mongoClient.list_database_names(), type(mongoClient.list_database_names()))
                    influencedRow.append(len(mongoClient.list_database_names()))
                    cursorDescription.append((('database',),))
                    # print(cursorDescription)
                elif sql.lower()[:3] == 'use':
                    databaseName = "".join(letter if letter != ';' else '' for letter in sql[4:])
                    db = mongoClient[databaseName]
                    influencedRow.append(0)
                    cursorDescription.append(None)
                else:
                    mongoQuery = sql2MongoShell(sql)
                    # print(mongoQuery)
                    mongoCursor = eval(mongoQuery)
                    mongoListCursor = list(mongoCursor)
                    influencedRow.append(len(mongoListCursor))

                    tempDescription = []
                    for attribute in list(mongoListCursor[0].keys()):
                        tempDescription.append((attribute,))
                    tempDescription = tuple(tempDescription)
                    cursorDescription.append(tempDescription)
                    # exit()
            else:
                cursor.execute(sql)
        except Exception as e:
            responseStatus = 1
            traceback.print_exc()
            return JsonResponse({'responseStatus': responseStatus, 'errorDetails': str(e)})
        endTime = time.time()
        totalExecutionTime += endTime - startTime
        executionTime.append(str(round(endTime - startTime, 2)) + ' s')

        # influencedRow = []
        # cursorDescription = []
        if databaseType != 'mongodb':
            influencedRow.append(cursor.rowcount)
            cursorDescription.append(cursor.description)
            # print(cursor.rowcount, cursor.description)
            if databaseType == 'mysql':
                while cursor.nextset():
                    influencedRow.append(cursor.rowcount)
                    cursorDescription.append(cursor.description)

        totalRecords.append(influencedRow)
        executedTimeStamp.append(datetime.now().strftime("%m/%d/%Y %H:%M:%S"))

        try:
            # change the color of keywords and identifier in the query
            colorQuery = ""
            keywordColor = "rgb(43, 51, 179)"
            identifierColor = "rgb(134, 179, 0)"
            for token in sqlparse.parse(sql)[0].flatten():
                if token.ttype in sqlparse.tokens.Keyword or token.ttype in sqlparse.tokens.Punctuation:
                    colorQuery += f"<span style='color: {keywordColor}'>{token.value}</span>"
                elif token.ttype in sqlparse.tokens.Name or token.ttype in sqlparse.tokens.Wildcard:
                    colorQuery += f"<span style='color: {identifierColor}'>{token.value}</span>"
                elif token.ttype is sqlparse.tokens.Whitespace:
                    colorQuery += '&nbsp;'
                else:
                    colorQuery += token.value
            colorQuery = colorQuery.replace("\n", "</br>")
            displayedQuery.append(colorQuery)

            # DML (INSERT, UPDATE) will use "affected", DQL (SELECT) will use "retrieved"
            tempRowResult = []
            for i in range(len(influencedRow)):
                if influencedRow[i] == 0 or influencedRow[i] == -1:
                    tempRowResult.append(None)
                elif influencedRow[i] == -1:
                    temp = f"{influencedRow[i]} row "
                    temp += "retrieved" if cursorDescription[i] else "affected"
                    tempRowResult.append(temp)
                else:
                    temp = f"{influencedRow[i]} rows "
                    temp += "retrieved" if cursorDescription[i] else "affected"
                    tempRowResult.append(temp)
            influencedRowResult.append(tempRowResult)
        except Exception as e:
            responseStatus = 1
            traceback.print_exc()
            return JsonResponse({'responseStatus': responseStatus, 'errorDetails': str(e)})
        try:
            if databaseType == 'mysql':
                queryResult.append(cursor.fetchmany(size=100))
                print(queryResult)
            elif databaseType == 'redshift':
                # no result will be fetched if the last query is DML (INSERT, UPDATE)
                if cursor.description:
                    # if cursor.description is not None, then it means the last query is DQL (SELECT)
                    queryResult.append(cursor.fetchmany(size=100))
                else:
                    queryResult.append(())
            elif databaseType == 'mongodb':
                if mongoListCursor:
                    tempResult = []
                    for row in mongoListCursor[:100]:
                        tempTuple = []
                        for k, v in row.items():
                            if k == '_id':
                                tempTuple.append(str(v))
                            else:
                                tempTuple.append(v)
                        tempTuple = tuple(tempTuple)
                        tempResult.append(tempTuple)
                        # tempResult.append(tuple(row.values()))
                    queryResult.append(tuple(tempResult))
                else:
                    queryResult.append(tuple())
        except Exception as e:
            responseStatus = 1
            traceback.print_exc()
            return JsonResponse({'responseStatus': responseStatus, 'errorDetails': str(e)})
        try:
            tempResultAttribute = []
            for description in cursorDescription:
                if description:
                    tempResultAttribute.append([attribute[0] for attribute in description])
                else:
                    tempResultAttribute.append(None)
            resultAttribute.append(tempResultAttribute)
        except Exception as e:
            responseStatus = 1
            traceback.print_exc()
            return JsonResponse({'responseStatus': responseStatus, 'errorDetails': str(e)})

    try:
        for i in range(len(influencedRowResult)):
            print(f'Executed Query: {query[i]}')
            print(f'Displayed Query: {displayedQuery[i]}')
            print(f'Influenced Row: {influencedRowResult[i]}')
            print(f'Result Attributes: {resultAttribute[i]}')
            print(f'Query Result: {queryResult[i][:100]}')  # limit query result to 100 rows
            print()
        print(f'Total Execution Time: {round(totalExecutionTime, 2)} s')
    except Exception as e:
        responseStatus = 1
        traceback.print_exc()
        return JsonResponse({'responseStatus': responseStatus, 'errorDetails': str(e)})

    try:
        if databaseType == 'mysql':
            cursor.execute('select database()')
            currentDatabase = cursor.fetchone()[0]
        elif databaseType == 'redshift':
            cursor.execute('select current_database()')
            currentDatabase = cursor.fetchone()[0]
        elif databaseType == 'mongodb':
            currentDatabase = db.name
    except Exception as e:
        responseStatus = 1
        traceback.print_exc()
        return JsonResponse({'responseStatus': responseStatus, 'errorDetails': str(e)})

    return JsonResponse(
        {'tableQuery': tableQuery,
         'displayedQuery': displayedQuery,
         'totalRecords': totalRecords,
         'executedTimeStamp': executedTimeStamp,
         'influencedRowResult': influencedRowResult,
         'resultAttribute': resultAttribute,
         'queryResult': queryResult,
         'executionTime': executionTime,
         'totalExecutionTime': str(round(totalExecutionTime, 2)) + ' s',
         'currentDatabase': str(currentDatabase)})
