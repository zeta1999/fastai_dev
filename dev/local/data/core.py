#AUTOGENERATED! DO NOT EDIT! File to edit: dev/05_data_core.ipynb (unless otherwise specified).

__all__ = ['show_batch', 'show_results', 'TfmdDL', 'DataBunch', 'FilteredBase', 'TfmdList', 'decode_at', 'show_at',
           'DataSource', 'test_set', 'test_dl']

#Cell
from ..torch_basics import *
from ..test import *
from .load import *

#Cell
@typedispatch
def show_batch(x, y, samples, ctxs=None, max_n=10, **kwargs):
    if ctxs is None: ctxs = Inf.nones
    for i in range_of(samples[0]):
        ctxs = [b.show(ctx=c, **kwargs) for b,c,_ in zip(samples.itemgot(i),ctxs,range(max_n))]
    return ctxs

#Cell
@typedispatch
def show_results(x, y, samples, outs, ctxs=None, max_n=10, **kwargs):
    if ctxs is None: ctxs = Inf.nones
    for i in range(len(samples[0])):
        ctxs = [b.show(ctx=c, **kwargs) for b,c,_ in zip(samples.itemgot(i),ctxs,range(max_n))]
    for i in range(len(outs[0])):
        ctxs = [b.show(ctx=c, **kwargs) for b,c,_ in zip(outs.itemgot(i),ctxs,range(max_n))]
    return ctxs

#Cell
_batch_tfms = ('after_item','before_batch','after_batch')

#Cell
@delegates()
class TfmdDL(DataLoader):
    "Transformed `DataLoader`"
    def __init__(self, dataset, bs=16, shuffle=False, num_workers=None, **kwargs):
        if num_workers is None: num_workers = min(16, defaults.cpus)
        for nm in _batch_tfms:
            kwargs[nm] = Pipeline(kwargs.get(nm,None), as_item=(nm=='before_batch'))
        super().__init__(dataset, bs=bs, shuffle=shuffle, num_workers=num_workers, **kwargs)
        for nm in _batch_tfms: kwargs[nm].setup(self)

    def _one_pass(self):
        its = self.after_batch(self.do_batch([self.do_item(0)]))
        self._device = find_device(its)
        self._n_inp = 1 if not isinstance(its, (list,tuple)) or len(its)==1 else len(its)-1
        self._retain_dl = partial(retain_types, typs=mapped(type,its))

    def _retain_dl(self,b):
        self._one_pass()
        # we just replaced ourselves, so this is *not* recursive! :)
        return self._retain_dl(b)

    def before_iter(self):
        super().before_iter()
        split_idx = getattr(self.dataset, 'split_idx', None)
        for nm in _batch_tfms:
            f = getattr(self,nm)
            if isinstance(f,Pipeline): f.split_idx=split_idx

    def decode(self, b): return self.before_batch.decode(self.after_batch.decode(self._retain_dl(b)))
    def decode_batch(self, b, max_n=10, full=True): return self._decode_batch(self.decode(b), max_n, full)

    def _decode_batch(self, b, max_n=10, full=True):
        f = self.after_item.decode
        f = compose(f, partial(getattr(self.dataset,'decode',noop), full = full))
        return L(batch_to_samples(b, max_n=max_n)).map(f)

    def _pre_show_batch(self, b, max_n=10):
        b = self.decode(b)
        if hasattr(b, 'show'): return b,None,None
        its = self._decode_batch(b, max_n, full=False)
        if not is_listy(b): b,its = [b],L((o,) for o in its)
        return detuplify(b[:self.n_inp]),detuplify(b[self.n_inp:]),its

    def show_batch(self, b=None, max_n=10, ctxs=None, **kwargs):
        "Show `b` (defaults to `one_batch`), a list of lists of pipeline outputs (i.e. output of a `DataLoader`)"
        if b is None: b = self.one_batch()
        show_batch(*self._pre_show_batch(b, max_n=max_n), ctxs=ctxs, max_n=max_n, **kwargs)

    def show_results(self, b, out, max_n=10, ctxs=None, **kwargs):
        x,y,its = self._pre_show_batch(b, max_n=max_n)
        b_out = b[:self.n_inp] + (tuple(out) if is_listy(out) else (out,))
        x1,y1,outs = self._pre_show_batch(b_out, max_n=max_n)
        if its is not None:
            show_results(x, y, its, outs.itemgot(slice(self.n_inp,None)), ctxs=ctxs, max_n=max_n, **kwargs)
        #its None means that a batch knows how to show itself as a whole, so we pass x, x1
        else: show_results(x, x1, its, outs, ctxs=ctxs, max_n=max_n, **kwargs)

    @property
    def device(self):
        if not hasattr(self, '_device'): _ = self._one_pass()
        return self._device

    @property
    def n_inp(self):
        if hasattr(self.dataset, 'n_inp'): return self.dataset.n_inp
        if not hasattr(self, '_n_inp'): self._one_pass()
        return self._n_inp

#Cell
@docs
class DataBunch(GetAttr):
    "Basic wrapper around several `DataLoader`s."
    _default='train_dl'

    def __init__(self, *dls): self.dls = dls
    def __getitem__(self, i): return self.dls[i]

    def new_empty(self):
        dls = [dl.new(dl.dataset.new_empty()) for dl in self.dls]
        return type(self)(*dls)

    train_dl,valid_dl = add_props(lambda i,x: x[i])
    train_ds,valid_ds = add_props(lambda i,x: x[i].dataset)

    @classmethod
    @delegates(TfmdDL.__init__)
    def from_dblock(cls, dblock, source, type_tfms=None, item_tfms=None, batch_tfms=None, **kwargs):
        return dblock.databunch(source, type_tfms=type_tfms, item_tfms=item_tfms, batch_tfms=batch_tfms, **kwargs)

    _docs=dict(__getitem__="Retrieve `DataLoader` at `i` (`0` is training, `1` is validation)",
               train_dl="Training `DataLoader`",
               valid_dl="Validation `DataLoader`",
               train_ds="Training `Dataset`",
               valid_ds="Validation `Dataset`",
               new_empty="Create a new empty version of `self` with the same transforms",
               from_dblock="Create a databunch from a given `dblock`")

#Cell
class FilteredBase:
    "Base class for lists with subsets"
    _dl_type = TfmdDL
    def __init__(self, *args, dl_type=None, **kwargs):
        if dl_type is not None: self._dl_type = dl_type
        self.databunch = delegates(self._dl_type.__init__)(self.databunch)
        super().__init__(*args, **kwargs)

    @property
    def n_subsets(self): return len(self.splits)
    def _new(self, items, **kwargs): return super()._new(items, splits=self.splits, **kwargs)
    def subset(self): raise NotImplemented

    def databunch(self, bs=16, val_bs=None, shuffle_train=True, n=None, dl_type=None, dl_kwargs=None, **kwargs):
        if dl_kwargs is None: dl_kwargs = [{}] * self.n_subsets
        ns = self.n_subsets-1
        bss = [bs] + [2*bs]*ns if val_bs is None else [bs] + [val_bs]*ns
        shuffles = [shuffle_train] + [False]*ns
        if dl_type is None: dl_type = self._dl_type
        dls = [dl_type(self.subset(i), bs=b, shuffle=s, drop_last=s, n=n if i==0 else None, **kwargs, **dk)
               for i,(b,s,dk) in enumerate(zip(bss,shuffles,dl_kwargs))]
        return DataBunch(*dls)

FilteredBase.train,FilteredBase.valid = add_props(lambda i,x: x.subset(i), 2)

#Cell
class TfmdList(FilteredBase, L):
    "A `Pipeline` of `tfms` applied to a collection of `items`"
    _default='tfms'
    def __init__(self, items, tfms, use_list=None, do_setup=True, as_item=True, split_idx=None, train_setup=True, splits=None):
        super().__init__(items, use_list=use_list)
        self.splits = L([slice(None),[]] if splits is None else splits).map(mask2idxs)
        if isinstance(tfms,TfmdList): tfms = tfms.tfms
        if isinstance(tfms,Pipeline): do_setup=False
        self.tfms = Pipeline(tfms, as_item=as_item, split_idx=split_idx)
        if do_setup: self.setup(train_setup=train_setup)

    def _new(self, items, **kwargs): return super()._new(items, tfms=self.tfms, do_setup=False, **kwargs)
    def subset(self, i): return self._new(self._get(self.splits[i]), split_idx=i)
    def _after_item(self, o): return self.tfms(o)
    def __repr__(self): return f"{self.__class__.__name__}: {self.items}\ntfms - {self.tfms.fs}"
    def __iter__(self): return (self[i] for i in range(len(self)))
    def show(self, o, **kwargs): return self.tfms.show(o, **kwargs)
    def decode(self, x, **kwargs): return self.tfms.decode(x, **kwargs)
    def __call__(self, x, **kwargs): return self.tfms.__call__(x, **kwargs)
    def setup(self, train_setup=True): self.tfms.setup(getattr(self,'train',self) if train_setup else self)
    def overlapping_splits(self): return L(Counter(self.splits.concat()).values()).filter(gt(1))

    def __getitem__(self, idx):
        res = super().__getitem__(idx)
        if self._after_item is None: return res
        return self._after_item(res) if is_indexer(idx) else res.map(self._after_item)

#Cell
def decode_at(o, idx):
    "Decoded item at `idx`"
    return o.decode(o[idx])

#Cell
def show_at(o, idx, **kwargs):
    "Show item at `idx`",
    return o.show(o[idx], **kwargs)

#Cell
@docs
@delegates(TfmdList)
class DataSource(FilteredBase):
    "A dataset that creates a tuple from each `tfms`, passed thru `item_tfms`"
    def __init__(self, items=None, tfms=None, tls=None, n_inp=None, dl_type=None, **kwargs):
        super().__init__(dl_type=dl_type)
        self.tls = L(tls if tls else [TfmdList(items, t, **kwargs) for t in L(ifnone(tfms,[None]))])
        self.n_inp = (1 if len(self.tls)==1 else len(self.tls)-1) if n_inp is None else n_inp

    def __getitem__(self, it):
        res = tuple([tl[it] for tl in self.tls])
        return res if is_indexer(it) else list(zip(*res))

    def __getattr__(self,k): return gather_attrs(self, k, 'tls')
    def __dir__(self): return super().__dir__() + gather_attr_names(self, 'tls')
    def __len__(self): return len(self.tls[0])
    def __iter__(self): return (self[i] for i in range(len(self)))
    def __repr__(self): return coll_repr(self)
    def decode(self, o, full=True): return tuple(tl.decode(o_, full=full) for o_,tl in zip(o,tuplify(self.tls, match=o)))
    def subset(self, i): return type(self)(tls=L(tl.subset(i) for tl in self.tls), n_inp=self.n_inp)
    def _new(self, items, *args, **kwargs): return super()._new(items, tfms=self.tfms, do_setup=False, **kwargs)
    def overlapping_splits(self): return self.tls[0].overlapping_splits()
    @property
    def splits(self): return self.tls[0].splits
    @property
    def split_idx(self): return self.tls[0].tfms.split_idx
    @property
    def items(self): return self.tls[0].items
    @items.setter
    def items(self, v):
        for tl in self.tls: tl.items = v

    def show(self, o, ctx=None, **kwargs):
        for o_,tl in zip(o,self.tls): ctx = tl.show(o_, ctx=ctx, **kwargs)
        return ctx

    def new_empty(self):
        tls = [tl._new([], split_idx=tl.split_idx) for tl in self.tls]
        return type(self)(tls=tls, n_inp=self.n_inp)

    _docs=dict(
        decode="Compose `decode` of all `tuple_tfms` then all `tfms` on `i`",
        show="Show item `o` in `ctx`",
        databunch="Get a `DataBunch`",
        overlapping_splits="All splits that are in more than one split",
        subset="New `DataSource` that only includes subset `i`",
        new_empty="Create a new empty version of the `self`, keeping only the transforms")

#Cell
def test_set(dsrc, test_items, rm_tfms=0):
    "Create a test set from `test_items` using validation transforms of `dsrc`"
    test_tls = [tl._new(test_items, split_idx=1) for tl in dsrc.tls[:dsrc.n_inp]]
    rm_tfms = tuplify(rm_tfms, match=test_tls)
    for i,j in enumerate(rm_tfms): test_tls[i].tfms.fs = test_tls[i].tfms.fs[j:]
    return DataSource(tls=test_tls)

#Cell
@delegates(TfmdDL.__init__)
def test_dl(dbunch, test_items, rm_type_tfms=0, **kwargs):
    "Create a test dataloader from `test_items` using validation transforms of `dbunch`"
    test_ds = test_set(dbunch.valid_ds, test_items, rm_tfms=rm_type_tfms) if isinstance(dbunch.valid_ds, DataSource) else test_items
    return dbunch.valid_dl.new(test_ds, **kwargs)