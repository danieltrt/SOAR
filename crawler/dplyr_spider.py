import re
import json
import os
from scrapy.spiders import Rule, CrawlSpider
from scrapy.crawler import Crawler, CrawlerProcess
from scrapy.linkextractors import LinkExtractor
from w3lib.html import remove_tags
from crawler.utils import APIItem, nice_dump, process_code_info


class DplyrSpider(CrawlSpider):
    name = "dplyr"
    version = "1.0.0"
    allowed_domains = ['dplyr.tidyverse.org']
    start_urls = [f'https://dplyr.tidyverse.org/reference/index.html']

    rules = [Rule(LinkExtractor(allow='reference/'),
                  callback='parse_api')]

    def parse_api(self, response):

        self.logger.info(f'Scraping {response.url}')

        item = APIItem()
        url = response.url
        url_split = url.split('/')
        id = url_split[len(url_split) - 1].replace('.html', '')

        if 'index' in id:
            return
        if id:
            item['item_id'] = id

        raw_code = response.css('pre.usage').get()
        if raw_code:
            code = remove_tags(raw_code).replace('\n', ' ')
        item['code'] = code

        description = remove_tags(response.css('div.ref-description').get()).replace('\n', ' ')
        item['description'] = description

        params = []

        param_table = response.css('table.ref-arguments')
        args = param_table.css('tr')
        for arg in args:
            arg_name = remove_tags(arg.css('th').get())
            arg_descr = remove_tags(arg.css('td').get()).replace('\n', ' ')
            params.append(arg_name + ': ' + arg_descr)
        item['parameters'] = params

        yield item

        # dealing with functions (methods without too much information)
        # fselectors = response.css('dl')
        # if fselectors:
        #     for fselector in fselectors:
        #         dt = fselector.css('dt')
        #         item = APIItem()
        #         item['library'] = 'pandas'
        #         try:
        #             self.parse_item(item, 'function', fselector)
        #             yield item
        #         except:
        #             try:
        #                 bad_id = fselector.css('dt').attrib['id']
        #                 print('######################### BAD FUNCTION: ' + bad_id + ' ######################')
        #             except:
        #                 pass


# class InnerSpider(CrawlSpider):


def preprocess_dplyr_data(raw_data_file):
    # load the raw data
    data = None
    with open(raw_data_file) as f:
        data = json.load(f)

    processed_data = []

    for item in data:
        # TODO: find better ways to exclude non-functions
        # if '(' not in item['code']:
        #     continue

        processed_item = dict()

        try:
            processed_item['id'] = item['item_id']
        except:
            continue
        # processed_item['type'] = item['item_type']
        # unify the notation for the code
        raw_code = item['code']
        code = item['item_id'] + raw_code[raw_code.find('('):raw_code.find(')') + 1]
        processed_item['code'] = code

        # extract the summary
        description = item['description']
        if 'Parameters' in description:
            summary = description.split('Parameters')[0]
        else:
            summary = description.split('.')[0]

        summary = description.split('. ')[0]
        # processed_item['example'] = item['example']

        if 'Example:' in item['description']:
            example = item['description'].split('Example:')[1]
            example = example.replace('&gt;', '')
            processed_item['example'] = example

        processed_item['summary'] = summary
        # processed_item['returns'] = item['returns']
        # processed_item['shape'] = item['shape']
        # if processed_item['type'] != 'class' and processed_item['type'] != 'attribute':

        processed_item['code-info'] = process_code_info(processed_item['code'])
        # add description to all the arguments
        arg_json: list = processed_item['code-info']['parameters']
        arg_names = list(map(lambda arg: arg['name'], arg_json))
        matching_result = dict()
        for i in range(len(arg_names)):
            arg_name = arg_names[i]
            start_mark = '\n' + arg_name + ' ('
            if i != len(arg_names) - 1:
                end_mark = '\n' + arg_names[i + 1] + ' ('
            else:
                end_mark = '\n\n'

            if (start_mark in description and end_mark in description):
                matching_result[arg_name] = '(' + description.split(start_mark)[1].split(end_mark)[0]

            else:
                if item['parameters']:
                    for item_param in item['parameters']:
                        item_param = item_param.replace('python:', '')
                        if ':' in item_param and arg_name in item_param:
                            item_param_name = item_param.split(':')[0].replace(' ', '')
                            if '(' in item_param_name:
                                item_param_name = item_param_name.split('(')[0]
                            if arg_name == item_param_name:
                                param_description = item_param.split(':')[1].replace(')', '')
                                matching_result[arg_name] = param_description

        for arg_dict in arg_json:
            name = arg_dict['name']
            if name in matching_result:
                arg_dict['description'] = matching_result[name]
            else:
                arg_dict['description'] = ''

        # augment the types of arguments with NL description
        for arg in arg_json:
            if arg['type'] == '':
                # TODO: figure out why it fails sometimes
                try:
                    description_types = arg['description'].split('(')[1].split(')')[0]
                    if 'int' in description_types:
                        arg['type'] = 'int'
                    elif 'float' in description_types:
                        arg['type'] = 'float'
                    elif 'bool' in description_types:
                        arg['type'] = 'bool'
                    elif 'Tensor' in description_types:
                        arg['type'] = 'tensor'
                    elif 'string' in description_types:
                        arg['type'] = 'string'
                    else:
                        arg['type'] = 'others'
                except IndexError:
                    arg['type'] = 'others'

            if arg['type'] == 'others':


                if item['parameters']:
                    for item_param in item['parameters']:
                        if arg['name'] in item_param:
                            if 'A data frame' in item_param:
                                arg['type'] = 'dataframe'
                            break

        processed_data.append(processed_item)

    preprocessed_json_file_name = 'preprocessed_' + raw_data_file
    if os.path.exists(preprocessed_json_file_name):
        os.remove(preprocessed_json_file_name)

    nice_dump(preprocessed_json_file_name, processed_data)


if __name__ == '__main__':
    json_file_name = 'dply_docs.json'

    # if os.path.exists(json_file_name):
    #     os.remove(json_file_name)
    #
    # spider = DplyrSpider()
    # process = CrawlerProcess({
    #     'USER_AGENT': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
    #     'FEED_FORMAT': 'json',
    #     'FEED_URI': json_file_name
    # })
    #
    # process.crawl(DplyrSpider)
    # process.start()
    # process.join()
    # print("crawling completes, starts preprocessing...")

    preprocess_dplyr_data(json_file_name)